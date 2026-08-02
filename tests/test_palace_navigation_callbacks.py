import json

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


# ─── DELETE DRAWER ───


def _open_drawer_state(monkeypatch):
    import asyncio
    import handlers.palace.action_bar as ab
    from handlers.palace import navigation

    class FakeMCP:
        async def call_tool(self, name, args=None):
            if name == "mempalace_list_drawers":
                return (
                    '{"drawers": [{"closet_name": "Запись", "drawer_id": "d1"}], "count": 1}'
                )
            return '{"content": "текст записи"}'

    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMCP())
    monkeypatch.setattr(navigation, "_read_state", {})
    monkeypatch.setattr(navigation, "_user_context", {TEST_UID: {"wing": "w1", "room": "r1"}})
    msg = FakeMessage()
    cb = FakeCallback("p_gd:w1:r1:Запись", msg)
    asyncio.run(navigation.cb_get_drawer(cb))
    return navigation, msg


def test_cb_read_drawer_has_delete_button(monkeypatch):
    navigation, msg = _open_drawer_state(monkeypatch)
    data = _markup_data(msg)
    assert any(d.startswith("p_drdel:") for d in data)


def test_cb_drawer_delete_asks_confirmation(monkeypatch):
    import asyncio

    navigation, msg = _open_drawer_state(monkeypatch)
    cb = FakeCallback("p_drdel:0", msg)
    asyncio.run(navigation.cb_drawer_delete(cb))
    assert "Удалить запись" in msg.edited[-1]
    data = _markup_data(msg)
    assert "p_drdel_c:0" in data
    assert "p_drdel_x:0" in data


def test_cb_drawer_delete_confirm_removes(monkeypatch):
    import asyncio

    navigation, msg = _open_drawer_state(monkeypatch)

    class FakeMCPDelete:
        async def call_tool(self, name, args=None):
            assert args == {"drawer_id": "d1"}
            return '{"success": true}'

    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMCPDelete())
    cb = FakeCallback("p_drdel_c:0", msg)
    asyncio.run(navigation.cb_drawer_delete_confirm(cb))
    assert "Запись удалена" in msg.edited[-1]
    assert "p_rdb" in _markup_data(msg)
    assert TEST_UID not in navigation._read_state


def test_cb_drawer_delete_confirm_failure(monkeypatch):
    import asyncio

    navigation, msg = _open_drawer_state(monkeypatch)

    class FakeMCPDelete:
        async def call_tool(self, name, args=None):
            return '{"success": false, "error": "drawer not found"}'

    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMCPDelete())
    cb = FakeCallback("p_drdel_c:0", msg)
    asyncio.run(navigation.cb_drawer_delete_confirm(cb))
    assert "Не удалось удалить" in msg.edited[-1]
    assert "drawer not found" in msg.edited[-1]


def test_cb_drawer_delete_no_state(monkeypatch):
    import asyncio

    navigation, msg = _open_drawer_state(monkeypatch)
    navigation._read_state.pop(TEST_UID, None)
    cb = FakeCallback("p_drdel:0", msg)
    asyncio.run(navigation.cb_drawer_delete(cb))
    assert "Сессия истекла" in msg.edited[-1]


def test_cb_drawer_delete_cancel_returns_to_view(monkeypatch):
    import asyncio

    navigation, msg = _open_drawer_state(monkeypatch)
    cb = FakeCallback("p_drdel_x:0", msg)
    asyncio.run(navigation.cb_drawer_delete_cancel(cb))
    assert "текст записи" in msg.edited[-1]
    data = _markup_data(msg)
    assert any(d.startswith("ab_ai:") for d in data)
    assert any(d.startswith("p_drdel:") for d in data)


def test_show_drawers_page_preview_and_full_text_button(monkeypatch):
    import asyncio

    from handlers.palace import navigation

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return (
                '{"drawers": [{"closet_name": "Заметка", '
                '"content_preview": "превью контента записи", "drawer_id": "d1"}], '
                '"count": 1}'
            )

    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMCP())
    monkeypatch.setattr(navigation, "_drawer_list_state", {})
    msg = FakeMessage()
    cb = FakeCallback("p_rd_room:xyz", msg)
    asyncio.run(navigation.cb_open_room_drawer(cb))
    text = msg.edited[-1]
    assert "превью контента записи" in text
    data = _markup_data(msg)
    assert any(d.startswith("p_rd:") for d in data)
    assert "Полный текст" in "".join(
        b.text for row in msg.markups[-1].inline_keyboard for b in row
    )


# ─── LIST PAGINATION (total from MCP) ───


def test_drawers_list_shows_next_page_button(monkeypatch):
    import asyncio

    from handlers.palace import navigation

    drawers = [
        {"closet_name": None, "content_preview": f"превью {i}", "drawer_id": f"d{i}"}
        for i in range(5)
    ]

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return json.dumps({"drawers": drawers, "count": 5, "total": 20})

    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMCP())
    monkeypatch.setattr(navigation, "_drawer_list_state", {})
    msg = FakeMessage()
    cb = FakeCallback("p_rd_room:xyz", msg)
    asyncio.run(navigation.cb_open_room_drawer(cb))
    data = _markup_data(msg)
    assert "p_rdp:5" in data
    assert "(20 записей)" in msg.edited[-1]


def test_drawers_list_last_page_shows_prev_and_no_next(monkeypatch):
    import asyncio

    from handlers.palace import navigation

    drawers = [
        {"closet_name": None, "content_preview": f"превью {i}", "drawer_id": f"d{i}"}
        for i in range(5)
    ]

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return json.dumps({"drawers": drawers, "count": 5, "total": 20})

    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMCP())
    monkeypatch.setattr(navigation, "_drawer_list_state", {})
    monkeypatch.setattr(navigation, "_user_context", {TEST_UID: {"wing": "w1", "room": "r1"}})
    msg = FakeMessage()
    cb = FakeCallback("p_rdp:15", msg)
    asyncio.run(navigation.cb_read_drawer_page(cb))
    data = _markup_data(msg)
    assert "p_rdp:10" in data
    assert "p_rdp:20" not in data


def test_drawers_list_total_falls_back_to_count(monkeypatch):
    import asyncio

    from handlers.palace import navigation

    drawers = [
        {"closet_name": None, "content_preview": "п", "drawer_id": f"d{i}"}
        for i in range(2)
    ]

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return json.dumps({"drawers": drawers, "count": 2})

    monkeypatch.setattr(navigation, "get_mcp", lambda: FakeMCP())
    monkeypatch.setattr(navigation, "_drawer_list_state", {})
    msg = FakeMessage()
    cb = FakeCallback("p_rd_room:xyz", msg)
    asyncio.run(navigation.cb_open_room_drawer(cb))
    assert "(2 записей)" in msg.edited[-1]
    data = _markup_data(msg)
    assert "p_rdp:" not in data
