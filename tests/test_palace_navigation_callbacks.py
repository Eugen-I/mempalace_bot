import pytest

from handlers.palace.navigation import (
    _build_room_callback_data,
    _decode_room_callback_data,
    _decode_callback_part,
    _encode_callback_part,
)

from tests.test_action_bar import FakeCallback, FakeMessage, _markup_data, TEST_UID


@pytest.fixture(autouse=True)
def _allow_test_user(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {TEST_UID})
    yield


def test_callback_parts_round_trip_long_and_special_names():
    raw = "Очень длинное название крыла " + "x" * 80 + " : / ?"
    encoded = _encode_callback_part(raw)
    assert _decode_callback_part(encoded) == raw


def test_room_callback_data_round_trips_wing_and_room():
    wing = "Крыло с пробелами"
    room = "Комната: с/двоеточием и вопросом?"
    data = _build_room_callback_data(wing, room)
    decoded_wing, decoded_room = _decode_room_callback_data(data)
    assert decoded_wing == wing
    assert decoded_room == room


def test_cb_continue_read_legacy_degrades_with_alert():
    import asyncio
    from handlers.palace import navigation

    cb = FakeCallback("p_cr:3500")
    asyncio.run(navigation.cb_continue_read(cb))
    assert cb.answered is not None
    text, kwargs = cb.answered
    assert kwargs.get("show_alert") is True
    assert "откройте запись заново" in text


def test_cb_get_drawer_long_content_paginates(monkeypatch):
    import asyncio
    import handlers.palace.action_bar as ab
    from handlers.palace import navigation

    long_text = "абвгд " * 400

    class FakeMCP:
        async def call_tool(self, name, args=None):
            if name == "mempalace_list_drawers":
                return (
                    '{"drawers": [{"closet_name": "Запись", "drawer_id": "d1"}], "count": 1}'
                )
            return '{"content": "%s"}' % long_text

    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMCP())
    monkeypatch.setattr(navigation, "_user_context", {TEST_UID: {"wing": "w1", "room": "r1"}})

    msg = FakeMessage()
    cb = FakeCallback("p_gd:w1:r1:Запись", msg)
    asyncio.run(navigation.cb_get_drawer(cb))
    data = _markup_data(msg)
    assert "Запись" in msg.edited[-1]
    assert any(d.startswith("ab_pg:") for d in data)
    assert any(d.startswith("ab_back:") for d in data)
    answer = ab.get_answer([d for d in data if d.startswith("ab_ai:")][0][6:])
    assert answer is not None
    assert answer.total_pages == 2
    assert answer.ctx["parent_cb"] == "p_rdb"


def test_cb_get_drawer_short_content_no_pagination(monkeypatch):
    import asyncio
    from handlers.palace import navigation

    class FakeMCP:
        async def call_tool(self, name, args=None):
            if name == "mempalace_list_drawers":
                return (
                    '{"drawers": [{"closet_name": "Запись", "drawer_id": "d1"}], "count": 1}'
                )
            return '{"content": "короткий текст"}'

    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMCP())
    monkeypatch.setattr(navigation, "_user_context", {TEST_UID: {"wing": "w1", "room": "r1"}})

    msg = FakeMessage()
    cb = FakeCallback("p_gd:w1:r1:Запись", msg)
    asyncio.run(navigation.cb_get_drawer(cb))
    data = _markup_data(msg)
    assert not any(d.startswith("ab_pg:") for d in data)
    assert any(d.startswith("ab_ai:") for d in data)


def test_cb_get_drawer_unknown_falls_back_to_search(monkeypatch):
    import asyncio
    from handlers.palace import navigation

    class FakeMCP:
        async def call_tool(self, name, args=None):
            if name == "mempalace_list_drawers":
                return '{"drawers": [{"closet_name": "Другая", "drawer_id": "d9"}], "count": 1}'
            return '{"found": 1}'

    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMCP())
    monkeypatch.setattr(navigation, "_user_context", {TEST_UID: {"wing": "w1", "room": "r1"}})

    msg = FakeMessage()
    cb = FakeCallback("p_gd:w1:r1:Нету", msg)
    asyncio.run(navigation.cb_get_drawer(cb))
    assert '{"found": 1}' in msg.edited[-1]
