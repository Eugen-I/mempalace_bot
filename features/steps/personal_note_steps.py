"""Шаги BDD для features/personal_note_room_select.feature.

Проверка Шага 1 ТЗ: выбор крыла через индекс pn_wing:{i}, чтобы
callback_data не превышал лимит Telegram в 64 байта.
"""
import asyncio
from types import SimpleNamespace

from behave import given, then, when

TEST_UID = 424242

LONG_WING = "ПСИХОАНАЛИТИЧЕСКАЯ МОДЕЛЬ ОПЫТА В ТВОРЧЕСТВЕ ФОТОГРАФА"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeMessage:
    def __init__(self):
        self.calls = []

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.calls.append(("edit", text, reply_markup))
        return self

    async def answer(self, text=None, parse_mode=None, reply_markup=None):
        self.calls.append(("answer", text or "", reply_markup))
        return self


class FakeCb:
    def __init__(self, data, msg):
        self.data = data
        self.message = msg
        self.answers = []
        self.from_user = SimpleNamespace(id=TEST_UID)

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))


def _kb_callback(msg):
    reply_markup = msg.calls[-1][2]
    if reply_markup is None:
        return []
    return [b.callback_data for row in reply_markup.inline_keyboard for b in row]


def _kb_labels(msg):
    reply_markup = msg.calls[-1][2]
    if reply_markup is None:
        return []
    return [b.text for row in reply_markup.inline_keyboard for b in row]


def _latest_text(msg):
    return msg.calls[-1][1]


def _clean():
    from handlers.personal_note import _note_data, _waiting_for_note

    _note_data.clear()
    _waiting_for_note.clear()


def _seed(taxonomy=None):
    _clean()
    from handlers.personal_note import _note_data

    _note_data[TEST_UID] = {
        "text": "Заметка",
        "raw": "Заметка",
        "wing": "личные_мысли",
        "room": "inbox",
        "taxonomy": taxonomy or {
            LONG_WING: {"Комната": {}},
            "my_notes": {"general": {}},
        },
    }


# ─── Given ───


@given('taxonomy содержит крыло «{wing}» длиной {size:d} байт')
def step_long_wing(context, wing, size):
    assert len(wing.encode("utf-8")) > 64
    _seed({wing: {"Комната": {}}})


@given('taxonomy содержит крылья «личные_мысли» и «{wing}» с индексами 0 и 1')
def step_two_wings(context, wing):
    assert wing == "ПСИХОАНАЛИТИЧЕСКАЯ ..."
    _seed({"личные_мысли": {"inbox": {}}, LONG_WING: {"Комната": {}}})
    from handlers.personal_note import _note_data

    _note_data[TEST_UID]["wings"] = ["личные_мысли", LONG_WING]


@given("сессия _note_data не существует для пользователя")
def step_no_session(context):
    _clean()


@given("список крыльев имеет длину 2 (индексы 0, 1)")
def step_wings_length(context):
    _seed({"личные_мысли": {}, LONG_WING: {}})
    from handlers.personal_note import _note_data

    _note_data[TEST_UID]["wings"] = ["личные_мысли", LONG_WING]


@given("taxonomy пуст для выбранного крыла")
def step_empty_taxonomy(context):
    _seed({})
    from handlers.personal_note import _note_data

    _note_data[TEST_UID]["wings"] = ["личные_мысли"]


# ─── When ───


@when('пользователь нажимает «✏️ Другая комната»')
def step_press_reclass(context):
    from handlers.personal_note import cb_pn_reclass

    context.msg = FakeMessage()
    context.cb = FakeCb("pn_reclass", context.msg)
    _run(cb_pn_reclass(context.cb))


@when("пользователь нажимает кнопку с callback_data pn_wing:1")
def step_press_wing_1(context):
    from handlers.personal_note import cb_pn_wing

    context.msg = FakeMessage()
    context.cb = FakeCb("pn_wing:1", context.msg)
    _run(cb_pn_wing(context.cb))


@when("пользователь нажимает кнопку с callback_data pn_wing:99")
def step_press_wing_99(context):
    from handlers.personal_note import cb_pn_wing

    context.msg = FakeMessage()
    context.cb = FakeCb("pn_wing:99", context.msg)
    _run(cb_pn_wing(context.cb))


@when("пользователь нажимает кнопку с callback_data pn_wing:abc")
def step_press_wing_abc(context):
    from handlers.personal_note import cb_pn_wing

    context.msg = FakeMessage()
    context.cb = FakeCb("pn_wing:abc", context.msg)
    _run(cb_pn_wing(context.cb))


@when("пользователь выбирает крыло с пустой taxonomy")
def step_press_wing_empty(context):
    from handlers.personal_note import cb_pn_wing

    context.msg = FakeMessage()
    context.cb = FakeCb("pn_wing:0", context.msg)
    _run(cb_pn_wing(context.cb))


# ─── Then / And ───


@then("бот показывает список крыльев")
def step_shows_wings(context):
    assert len(_kb_callback(context.msg)) >= 2


@then("каждый callback_data кнопки не длиннее 64 байт")
def step_cb_within_limit(context):
    for cd in _kb_callback(context.msg):
        assert len(cd.encode("utf-8")) <= 64


@then("полное имя длинного крыла отображается текстом кнопки")
def step_long_name_in_button(context):
    assert any(LONG_WING in t for t in _kb_labels(context.msg))


@then('бот показывает комнаты крыла «{wing}»')
def step_shows_rooms(context, wing):
    assert wing in _latest_text(context.msg)


@then("выбранное крыло сохранено в сессии")
def step_wing_saved(context):
    from handlers.personal_note import _note_data

    assert _note_data[TEST_UID]["wing"] == LONG_WING


@then("бот использует фолбэк-крыло «личные_мысли»")
def step_fallback_wing(context):
    from handlers.personal_note import _note_data

    assert _note_data[TEST_UID]["wing"] == "личные_мысли"


@then("бот использует комнату inbox")
def step_room_inbox(context):
    from handlers.personal_note import _note_data

    assert _note_data[TEST_UID]["room_list"] == ["inbox"]


@then("показывает кнопку «🆕 inbox»")
def step_shows_inbox_button(context):
    assert "🆕 inbox" in _kb_labels(context.msg)


@then('бот отвечает «Сессия истекла.»')
def step_session_expired(context):
    assert "Сессия истекла" in _latest_text(context.msg)