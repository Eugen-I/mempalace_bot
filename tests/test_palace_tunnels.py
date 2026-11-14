"""Unit tests for handlers.palace.tunnels."""

import asyncio

import pytest

from handlers.palace import tunnels as t


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=4242):
        self.from_user = FakeUser(uid)
        self.answers = []
        self.edits = []

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append((text, parse_mode, reply_markup))
        return self

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits.append((text, parse_mode, reply_markup))


class FakeCb:
    def __init__(self, uid=4242, data="", message=None):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = message or FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))


class FakeMCP:
    def __init__(self, result="{}", fail_on=None):
        self.result = result
        self.calls = []
        self.fail_on = fail_on

    async def call_tool(self, name, params=None):
        self.calls.append((name, params))
        if self.fail_on:
            raise RuntimeError(self.fail_on)
        return self.result


class FakeMCPSeq(FakeMCP):
    def __init__(self, results):
        self.results = list(results)
        self.calls = []
        self.fail_on = None

    async def call_tool(self, name, params=None):
        self.calls.append((name, params))
        return self.results.pop(0)


def _enable(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    monkeypatch.setattr(t, "safe_html_format", lambda x: x)


@pytest.fixture(autouse=True)
def _clean_state():
    from handlers.palace import shared as sh

    for key in ("_pending_mcp_input", "_tunnel_state", "_create_tunnel_state",
                "_room_cache"):
        sh.fsm.pop_data(4242, key)
    yield
    for key in ("_pending_mcp_input", "_tunnel_state", "_create_tunnel_state",
                "_room_cache"):
        sh.fsm.pop_data(4242, key)


def _kb_data(markup):
    if markup is None:
        return []
    return [b.callback_data for row in markup.inline_keyboard for b in row]


# ---------- _show_cross_rooms ----------


def test_show_cross_rooms_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(
        '[{"room": "комната б", "wing": "крыло"}, {"room": "комната а", "wing": "крыло"}]',
    )
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append((text, parse_mode, reply_markup))

    asyncio.run(t._show_cross_rooms(edit_func, 4242, "крыло", "комната а"))
    assert "Связанные комнаты" in edits[0][0]
    assert _kb_data(edits[0][2]) == ["p_crr:комната б", "p_tun"]


def test_show_cross_rooms_no_connected(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('[]')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append(text)

    asyncio.run(t._show_cross_rooms(edit_func, 4242, "крыло", "комната а"))
    assert edits[0] == "❌ Для комнаты «комната а» нет связанных комнат."


def test_show_cross_rooms_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(fail_on="mcp")
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append(text)

    asyncio.run(t._show_cross_rooms(edit_func, 4242, "крыло", "комната а"))
    assert edits[0] == "❌ Для комнаты «комната а» нет связанных комнат."


def test_show_cross_rooms_only_self(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('[{"room": "комната а", "wing": "крыло"}]')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append(text)

    asyncio.run(t._show_cross_rooms(edit_func, 4242, "крыло", "комната а"))
    assert edits[0] == "❌ Для «комната а» нет связанных комнат."


def test_show_cross_rooms_single_dict(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"room": "комната б", "wing": "крыло"}')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append((text, parse_mode, reply_markup))

    asyncio.run(t._show_cross_rooms(edit_func, 4242, "крыло", "комната а"))
    btn = edits[0][2].inline_keyboard[0][0]
    assert "комната б" in btn.text
    assert btn.callback_data == "p_crr:комната б"


def test_show_cross_rooms_non_dict_nodes(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('["строка", {"room": "комната б", "wing": "крыло"}]')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append((text, parse_mode, reply_markup))

    asyncio.run(t._show_cross_rooms(edit_func, 4242, "крыло", "комната а"))
    btn = edits[0][2].inline_keyboard[0][0]
    assert "комната б" in btn.text


# ---------- cb_find_tunnels_wing_b ----------


def test_cb_find_tunnels_wing_b(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_tfa_крыло а")
    asyncio.run(t.cb_find_tunnels_wing_b(cb))
    assert t._pending_mcp_input[4242] == "find_tunnels"
    assert "крыло а" in cb.message.edits[-1][0]


# ---------- cb_find_tunnels_result ----------


def test_cb_find_tunnels_result_success(monkeypatch):
    _enable(monkeypatch)
    t._tunnel_state[4242] = {"wing_a": "крыло а"}
    mcp = FakeMCP(
        '[{"room": "комната 1", "wings": ["крыло б"], "count": 3}]',
    )
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    captured = {}

    async def fake_finalize(uid, edit_func, text, is_html=False, ctx=None,
                            extra_rows=None):
        captured["uid"] = uid
        captured["text"] = text
        captured["ctx"] = ctx

    monkeypatch.setattr(
        "handlers.palace.action_bar.finalize_answer", fake_finalize,
    )
    cb = FakeCb(data="p_tfb_крыло б")
    asyncio.run(t.cb_find_tunnels_result(cb))
    assert mcp.calls[0] == (
        "mempalace_find_tunnels", {"wing_a": "крыло а", "wing_b": "крыло б"},
    )
    assert captured["uid"] == 4242
    assert "комната 1" in captured["text"]
    assert captured["ctx"] == {"parent_cb": "p_tun"}


def test_cb_find_tunnels_result_any_wing(monkeypatch):
    _enable(monkeypatch)
    t._tunnel_state[4242] = {"wing_a": "крыло а"}
    mcp = FakeMCP('[]')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tfb_-")
    asyncio.run(t.cb_find_tunnels_result(cb))
    assert mcp.calls[0][1] == {"wing_a": "крыло а"}
    assert cb.message.edits[-1][0] == "🔗 Туннелей не найдено."


def test_cb_find_tunnels_result_empty_raw(monkeypatch):
    _enable(monkeypatch)
    t._tunnel_state[4242] = {"wing_a": "крыло а"}
    mcp = FakeMCP("")
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tfb_б")
    asyncio.run(t.cb_find_tunnels_result(cb))
    assert cb.message.edits[-1][0] == "🔗 Туннелей не найдено."


def test_cb_find_tunnels_result_error(monkeypatch):
    _enable(monkeypatch)
    t._tunnel_state[4242] = {"wing_a": "крыло а"}
    mcp = FakeMCP(fail_on="mcp")
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tfb_б")
    asyncio.run(t.cb_find_tunnels_result(cb))
    assert "❌ Ошибка: mcp" in cb.message.edits[-1][0]


# ---------- cb_follow_tunnels_wing ----------


def test_cb_follow_tunnels_wing(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_to")
    asyncio.run(t.cb_follow_tunnels_wing(cb))
    assert t._pending_mcp_input[4242] == "follow_tunnels"
    assert "крыло" in cb.message.edits[-1][0]


# ---------- cb_follow_tunnels_room ----------


def test_cb_follow_tunnels_room_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"rooms": {"комната а": {}, "комната б": {}}}')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tow_крыло")
    asyncio.run(t.cb_follow_tunnels_room(cb))
    assert t._tunnel_state[4242] == {"wing_a": "крыло"}
    assert _kb_data(cb.message.edits[-1][2]) == [
        "p_tor:комната а", "p_tor:комната б", "p_tun",
    ]


def test_cb_follow_tunnels_room_no_rooms(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"rooms": {}}')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tow_крыло")
    asyncio.run(t.cb_follow_tunnels_room(cb))
    assert cb.message.edits[-1][0] == "❌ В крыле «крыло» нет комнат."


def test_cb_follow_tunnels_room_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(fail_on="mcp")
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tow_крыло")
    asyncio.run(t.cb_follow_tunnels_room(cb))
    assert cb.message.edits[-1][0] == "❌ В крыле «крыло» нет комнат."


# ---------- cb_follow_tunnels_result ----------


def test_cb_follow_tunnels_result_success(monkeypatch):
    _enable(monkeypatch)
    t._tunnel_state[4242] = {"wing_a": "крыло"}
    mcp = FakeMCP("результат")
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    captured = {}

    async def fake_finalize(uid, edit_func, text, is_html=False, ctx=None,
                            extra_rows=None):
        captured["uid"] = uid
        captured["text"] = text
        captured["ctx"] = ctx

    monkeypatch.setattr(
        "handlers.palace.action_bar.finalize_answer", fake_finalize,
    )
    cb = FakeCb(data="p_tor_комната а")
    asyncio.run(t.cb_follow_tunnels_result(cb))
    assert mcp.calls[0] == (
        "mempalace_follow_tunnels", {"wing": "крыло", "room": "комната а"},
    )
    assert captured["text"] == "результат"
    assert captured["ctx"] == {
        "wing": "крыло", "room": "комната а", "parent_cb": "p_tun",
    }


def test_cb_follow_tunnels_result_empty(monkeypatch):
    _enable(monkeypatch)
    t._tunnel_state[4242] = {"wing_a": "крыло"}
    mcp = FakeMCP("")
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    captured = {}

    async def fake_finalize(uid, edit_func, text, is_html=False, ctx=None,
                            extra_rows=None):
        captured["text"] = text

    monkeypatch.setattr(
        "handlers.palace.action_bar.finalize_answer", fake_finalize,
    )
    cb = FakeCb(data="p_tor_комната а")
    asyncio.run(t.cb_follow_tunnels_result(cb))
    assert captured["text"] == "❌ Нет результатов."


def test_cb_follow_tunnels_result_error(monkeypatch):
    _enable(monkeypatch)
    t._tunnel_state[4242] = {"wing_a": "крыло"}
    mcp = FakeMCP(fail_on="mcp")
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tor_комната а")
    asyncio.run(t.cb_follow_tunnels_result(cb))
    assert "❌ Ошибка: mcp" in cb.message.edits[-1][0]


# ---------- _show_wing_buttons_for_tunnel ----------


def test_show_wing_buttons_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"wings": {"крыло а": {}, "крыло б": {}}}')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append((text, parse_mode, reply_markup))

    ok = asyncio.run(t._show_wing_buttons_for_tunnel(edit_func, "tcs", 4242))
    assert ok is True
    assert _kb_data(edits[0][2]) == ["p_tcs_крыло а", "p_tcs_крыло б", "p_tun"]


def test_show_wing_buttons_exclude(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"wings": {"крыло а": {}, "крыло б": {}}}')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append((text, parse_mode, reply_markup))

    ok = asyncio.run(
        t._show_wing_buttons_for_tunnel(edit_func, "tctw", 4242, "крыло а"),
    )
    assert ok is True
    assert _kb_data(edits[0][2]) == ["p_tctw_крыло б", "p_tun"]


def test_show_wing_buttons_no_wings(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"wings": {}}')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append(text)

    ok = asyncio.run(t._show_wing_buttons_for_tunnel(edit_func, "tcs", 4242))
    assert ok is False
    assert edits[0] == "❌ Нет доступных крыльев."


def test_show_wing_buttons_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(fail_on="mcp")
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    edits = []

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append(text)

    ok = asyncio.run(t._show_wing_buttons_for_tunnel(edit_func, "tcs", 4242))
    assert ok is False
    assert edits[0] == "❌ Нет доступных крыльев."


# ---------- cb_create_tunnel_source_wing ----------


def test_cb_create_tunnel_source_wing(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"wings": {"крыло а": {}}}')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tc")
    asyncio.run(t.cb_create_tunnel_source_wing(cb))
    assert t._create_tunnel_state[4242] == {}
    assert "p_tcs_крыло а" in _kb_data(cb.message.edits[-1][2])


# ---------- cb_create_tunnel_source_room ----------


def test_cb_create_tunnel_source_room_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"rooms": {"комната а": {}, "комната б": {}}}')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tcs_крыло а")
    asyncio.run(t.cb_create_tunnel_source_room(cb))
    assert t._create_tunnel_state[4242]["source_wing"] == "крыло а"
    assert _kb_data(cb.message.edits[-1][2]) == [
        "p_tcsr_0", "p_tcsr_1", "p_tc",
    ]
    assert t._room_cache[4242] == [
        ("комната а", {}), ("комната б", {}),
    ]


def test_cb_create_tunnel_source_room_no_rooms(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"rooms": {}}')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tcs_крыло а")
    asyncio.run(t.cb_create_tunnel_source_room(cb))
    assert cb.message.edits[-1][0] == "❌ В крыле «крыло а» нет комнат."


def test_cb_create_tunnel_source_room_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(fail_on="mcp")
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tcs_крыло а")
    asyncio.run(t.cb_create_tunnel_source_room(cb))
    assert cb.message.edits[-1][0] == "❌ В крыле «крыло а» нет комнат."


# ---------- cb_create_tunnel_target_wing ----------


def test_cb_create_tunnel_target_wing_success(monkeypatch):
    _enable(monkeypatch)
    t._room_cache[4242] = [("комната а", {}), ("комната б", {})]
    t._create_tunnel_state[4242] = {"source_wing": "крыло а"}
    mcp = FakeMCP('{"wings": {"крыло б": {}, "крыло а": {}}}')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tcsr_1")
    asyncio.run(t.cb_create_tunnel_target_wing(cb))
    state = t._create_tunnel_state[4242]
    assert state["source_room"] == "комната б"
    assert state["source_idx"] == 1
    assert "крыло а" not in _kb_data(cb.message.edits[-1][2])
    assert "p_tctw_крыло б" in _kb_data(cb.message.edits[-1][2])


def test_cb_create_tunnel_target_wing_no_cache(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_tcsr_0")
    asyncio.run(t.cb_create_tunnel_target_wing(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла."


def test_cb_create_tunnel_target_wing_out_of_range(monkeypatch):
    _enable(monkeypatch)
    t._room_cache[4242] = [("комната а", {})]
    cb = FakeCb(data="p_tcsr_5")
    asyncio.run(t.cb_create_tunnel_target_wing(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла."


# ---------- cb_create_tunnel_target_room ----------


def test_cb_create_tunnel_target_room_success(monkeypatch):
    _enable(monkeypatch)
    t._create_tunnel_state[4242] = {"source_wing": "крыло а"}
    mcp = FakeMCP('{"rooms": {"комната ц": {}}}')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tctw_крыло б")
    asyncio.run(t.cb_create_tunnel_target_room(cb))
    state = t._create_tunnel_state[4242]
    assert state["target_wing"] == "крыло б"
    assert _kb_data(cb.message.edits[-1][2]) == ["p_tctr:0", "p_tc"]


def test_cb_create_tunnel_target_room_no_rooms(monkeypatch):
    _enable(monkeypatch)
    t._create_tunnel_state[4242] = {"source_wing": "крыло а"}
    mcp = FakeMCP('{"rooms": {}}')
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tctw_крыло б")
    asyncio.run(t.cb_create_tunnel_target_room(cb))
    assert cb.message.edits[-1][0] == "❌ В крыле «крыло б» нет комнат."


def test_cb_create_tunnel_target_room_error(monkeypatch):
    _enable(monkeypatch)
    t._create_tunnel_state[4242] = {"source_wing": "крыло а"}
    mcp = FakeMCP(fail_on="mcp")
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tctw_крыло б")
    asyncio.run(t.cb_create_tunnel_target_room(cb))
    assert cb.message.edits[-1][0] == "❌ В крыле «крыло б» нет комнат."


# ---------- cb_create_tunnel_label_prompt ----------


def test_cb_create_tunnel_label_prompt_success(monkeypatch):
    _enable(monkeypatch)
    t._room_cache[4242] = [("комната ц", {})]
    t._create_tunnel_state[4242] = {
        "source_wing": "крыло а",
        "source_room": "комната а",
        "target_wing": "крыло б",
    }
    cb = FakeCb(data="p_tctr:0")
    asyncio.run(t.cb_create_tunnel_label_prompt(cb))
    state = t._create_tunnel_state[4242]
    assert state["target_room"] == "комната ц"
    assert t._pending_mcp_input[4242] == "create_tunnel"
    body = cb.message.edits[-1][0]
    assert "Исходная: крыло а/комната а" in body
    assert "Целевая:  крыло б/комната ц" in body


def test_cb_create_tunnel_label_prompt_no_state(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_tctr:0")
    asyncio.run(t.cb_create_tunnel_label_prompt(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла. Начните заново."


def test_cb_create_tunnel_label_prompt_no_rooms(monkeypatch):
    _enable(monkeypatch)
    t._create_tunnel_state[4242] = {"source_wing": "крыло а"}
    cb = FakeCb(data="p_tctr:0")
    asyncio.run(t.cb_create_tunnel_label_prompt(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла. Начните заново."


def test_cb_create_tunnel_label_prompt_out_of_range(monkeypatch):
    _enable(monkeypatch)
    t._room_cache[4242] = [("комната ц", {})]
    t._create_tunnel_state[4242] = {
        "source_wing": "крыло а",
        "source_room": "комната а",
        "target_wing": "крыло б",
    }
    cb = FakeCb(data="p_tctr:5")
    asyncio.run(t.cb_create_tunnel_label_prompt(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла. Начните заново."


# ---------- not allowed ----------


@pytest.mark.parametrize(
    "data",
    ["p_tfa_крыло", "p_tfb_крыло", "p_to", "p_tow_крыло", "p_tor_комната",
     "p_tc", "p_tcs_крыло", "p_tcsr_0", "p_tctw_крыло", "p_tctr:0"],
)
def test_callbacks_not_allowed(monkeypatch, data):
    _enable(monkeypatch)
    cb = FakeCb(uid=999, data=data)
    asyncio.run(_dispatch(cb))
    assert cb.answered == [("❌ Нет доступа", True)]


async def _dispatch(cb):
    d = cb.data
    if d.startswith("p_tfa_"):
        await t.cb_find_tunnels_wing_b(cb)
    elif d.startswith("p_tfb_"):
        await t.cb_find_tunnels_result(cb)
    elif d.startswith("p_tow_"):
        await t.cb_follow_tunnels_room(cb)
    elif d.startswith("p_tor_"):
        await t.cb_follow_tunnels_result(cb)
    elif d.startswith("p_tcs_"):
        await t.cb_create_tunnel_source_room(cb)
    elif d.startswith("p_tcsr_"):
        await t.cb_create_tunnel_target_wing(cb)
    elif d.startswith("p_tctw_"):
        await t.cb_create_tunnel_target_room(cb)
    elif d.startswith("p_tctr:"):
        await t.cb_create_tunnel_label_prompt(cb)
    elif d == "p_to":
        await t.cb_follow_tunnels_wing(cb)
    elif d == "p_tc":
        await t.cb_create_tunnel_source_wing(cb)


def test_cb_follow_tunnels_result_colon_prefix(monkeypatch):
    """Регрессия: кнопки p_tor:<room> с двоеточием должны обрабатываться."""
    _enable(monkeypatch)
    t._tunnel_state[4242] = {"wing_a": "крыло"}
    mcp = FakeMCP("туннель найден")
    monkeypatch.setattr(t, "get_mcp", lambda: mcp)
    captured = {}

    async def fake_finalize(uid, edit_func, text, is_html=False, ctx=None,
                            extra_rows=None):
        captured["text"] = text
        captured["ctx"] = ctx

    monkeypatch.setattr(
        "handlers.palace.action_bar.finalize_answer", fake_finalize,
    )
    cb = FakeCb(data="p_tor:комната а")
    asyncio.run(t.cb_follow_tunnels_result(cb))
    assert captured["text"] == "туннель найден"
    assert captured["ctx"] == {"wing": "крыло", "room": "комната а", "parent_cb": "p_tun"}


def test_cb_cross_room_select(monkeypatch):
    """Клик по связанной комнате p_crr:<room> открывает её ящики."""
    _enable(monkeypatch)
    t._tunnel_state[4242] = {"cross_rooms": {"комната б": "крыло"}}
    opened = []

    async def fake_drawers_page(edit_func, uid, wing, room, offset=0):
        opened.append((uid, wing, room, offset))

    monkeypatch.setattr(
        "handlers.palace.navigation._show_drawers_page", fake_drawers_page,
    )
    cb = FakeCb(data="p_crr:комната б")
    asyncio.run(t.cb_cross_room_select(cb))
    assert opened == [(4242, "крыло", "комната б", 0)]
