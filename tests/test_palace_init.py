"""Unit tests for handlers/palace/__init__.py."""

import asyncio
import importlib
import json
import sys
from types import SimpleNamespace

import pytest

palace = importlib.import_module("handlers.palace")
from handlers.palace import navigation, shared as sh


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
        return self


class FakeCb:
    def __init__(self, uid=4242, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))


class FakeMCPSeq:
    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    async def call_tool(self, name, args=None):
        self.calls.append((name, args))
        result = self.results.pop(0)
        if callable(result):
            result = result()
        if isinstance(result, Exception):
            raise result
        return result


def _enable(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})


@pytest.fixture(autouse=True)
def _clean_store():
    sh.fsm.clear(4242)
    sh.fsm.clear(999)
    yield
    sh.fsm.clear(4242)
    sh.fsm.clear(999)


@pytest.fixture(autouse=True)
def _tmp_interpretation(monkeypatch, tmp_path):
    from services import interpreter

    monkeypatch.setattr(
        interpreter, "PAIRS_FILE", str(tmp_path / "interpretation.json"),
    )
    interpreter._pairs.clear()
    interpreter._loaded = False
    yield
    interpreter._pairs.clear()
    interpreter._loaded = False


def _kb_data(markup):
    if markup is None:
        return []
    if hasattr(markup, "as_markup"):
        markup = markup.as_markup()
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def _json_wings(d):
    return json.dumps({"wings": d})


def _json_rooms(d):
    return json.dumps({"rooms": d})


class FakeAnswerMsg:
    def __init__(self):
        self.answers = []
        self.edits = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)
        return self

    async def edit_text(self, text, **kwargs):
        self.edits.append((text, kwargs))


class FakeAnswerFactory:
    def __init__(self, msg):
        self.msg = msg

    async def __call__(self, text):
        return self.msg


def _run_process(monkeypatch, uid, text, results=None, mcp=None):
    if mcp is None:
        mcp = FakeMCPSeq(results or [])
    if monkeypatch is not None:
        monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        uid, text, FakeAnswerFactory(msg),
    ))
    return result, msg, mcp


def _capture_finalize(monkeypatch, store):
    async def fake_finalize(uid, edit_func, text, **kwargs):
        store["text"] = text
        store["ctx"] = kwargs.get("ctx", {})
        store["is_html"] = kwargs.get("is_html", False)
        store["extra_rows"] = kwargs.get("extra_rows", [])
        store["title"] = kwargs.get("title")
        return None

    monkeypatch.setattr("handlers.palace.action_bar.finalize_answer", fake_finalize)


# ---------- cmd_palace ----------


def test_cmd_palace(monkeypatch):
    _enable(monkeypatch)
    msg = FakeMessage()
    asyncio.run(palace.cmd_palace(msg))
    text, pm, markup = msg.answers[-1]
    assert "MemPalace — управление" in text
    assert pm == "Markdown"
    assert _kb_data(markup) == [
        "palace_status", "p_nav", "p_kg", "palace_admin",
        "palace_instructions", "palace_main_menu",
    ]


# ---------- cb_palace_back ----------


def test_cb_palace_back(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="palace_back")
    asyncio.run(palace.cb_palace_back(cb))
    assert cb.answered == [(None, None)]
    text, pm, markup = cb.message.edits[-1]
    assert "MemPalace — управление" in text
    assert pm == "HTML"
    assert _kb_data(markup)[0] == "palace_status"


# ---------- cb_palace_main_menu ----------


def test_cb_palace_main_menu_via_main_module(monkeypatch):
    _enable(monkeypatch)
    called = []

    async def fake_cmd_start(message):
        called.append(message)

    fake_mod = SimpleNamespace(cmd_start=fake_cmd_start)
    monkeypatch.setitem(sys.modules, "__main__", fake_mod)
    cb = FakeCb(data="palace_main_menu")
    asyncio.run(palace.cb_palace_main_menu(cb))
    assert called == [cb.message]


def test_cb_palace_main_menu_fallback_import(monkeypatch):
    _enable(monkeypatch)
    called = []

    async def fake_cmd_start(message):
        called.append(message)

    fake_main = SimpleNamespace(cmd_start=fake_cmd_start)
    monkeypatch.setitem(sys.modules, "main", fake_main)
    cb = FakeCb(data="palace_main_menu")
    asyncio.run(palace.cb_palace_main_menu(cb))
    assert called == [cb.message]


# ---------- no action ----------


def test_process_mcp_text_input_no_action():
    result, msg, _ = _run_process(None, 4242, "привет")
    assert result is False
    assert msg.answers == []
    assert msg.edits == []


# ---------- list_rooms: "*" ----------


def test_list_rooms_all_wings(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_wings({"b": 2, "a": 5})])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    sh.fsm.update_data(4242, _pending_mcp_input="list_rooms")
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "*", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert captured["is_html"] is True
    assert "b" in captured["text"]
    assert captured["ctx"] == {"parent_cb": "p_wing"}
    rows = [[b.callback_data for b in row] for row in captured["extra_rows"]]
    assert rows[0][0].startswith("p_rs_:")
    assert sh.fsm.get_data(4242).get("_pending_mcp_input") is None
    assert sh._wing_cache.get(4242) == ["a", "b"]


def test_list_rooms_all_wings_list_form(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_wings(["a", "b"])])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    sh._pending_mcp_input[4242] = "list_rooms"
    msg = FakeAnswerMsg()
    asyncio.run(palace.process_mcp_text_input(
        4242, "*", FakeAnswerFactory(msg),
    ))
    assert sh._wing_cache.get(4242) == ["a", "b"]


# ---------- list_rooms: specific wing ----------


def test_list_rooms_wing(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_rooms({"комната": 3, "другая": 1})])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    sh._pending_mcp_input[4242] = "list_rooms"
    msg = FakeAnswerMsg()
    asyncio.run(palace.process_mcp_text_input(
        4242, "Философия", FakeAnswerFactory(msg),
    ))
    assert captured["ctx"] == {"parent_cb": "p_nav"}
    assert "Комнаты крыла «philosophy»" in captured["text"]
    assert "комната" in captured["text"]
    rows = [[b.callback_data for b in row] for row in captured["extra_rows"]]
    assert rows[0][0].startswith("p_rd_room:")


def test_list_rooms_wing_truncated(monkeypatch):
    _enable(monkeypatch)
    rooms = {f"r{i}": 1 for i in range(51)}
    mcp = FakeMCPSeq([_json_rooms(rooms)])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    sh._pending_mcp_input[4242] = "list_rooms"
    msg = FakeAnswerMsg()
    asyncio.run(palace.process_mcp_text_input(
        4242, "философия", FakeAnswerFactory(msg),
    ))
    assert "и ещё 1 комнат" in captured["text"]


# ---------- traverse ----------


def test_traverse_error_with_suggestions(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({
        "error": "Комната не найдена", "suggestions": ["сны", "философия"],
    })])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    sh._pending_mcp_input[4242] = "traverse_start"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "сны", FakeAnswerFactory(msg),
    ))
    assert result is True
    text = msg.edits[-1][0]
    assert "Комната не найдена" in text
    assert "• сны" in text


def test_traverse_results(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps([
        {"room": "сны", "wings": ["психология"], "hop": 1, "count": 3},
    ])])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    sh._pending_mcp_input[4242] = "traverse"
    msg = FakeAnswerMsg()
    asyncio.run(palace.process_mcp_text_input(
        4242, "сны", FakeAnswerFactory(msg),
    ))
    assert "Траверс от комнаты «dreams»" in captured["text"]
    assert "сны" in captured["text"]


def test_traverse_no_results(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps([])])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    sh._pending_mcp_input[4242] = "traverse_start"
    msg = FakeAnswerMsg()
    asyncio.run(palace.process_mcp_text_input(
        4242, "сны", FakeAnswerFactory(msg),
    ))
    assert msg.edits[-1][0] == "[]"


# ---------- save_quote ----------


def test_save_quote(monkeypatch):
    _enable(monkeypatch)
    sh.fsm.update_data(4242, _save_state={"wing": "w", "room": "r"})
    called = []

    async def fake_wings(edit_func, uid):
        called.append((edit_func, uid))

    monkeypatch.setattr("handlers.palace._show_save_wings", fake_wings)
    sh._pending_mcp_input[4242] = "save_quote"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "  цитата  ", FakeAnswerFactory(msg),
    ))
    assert result is True
    state = sh._save_state.get(4242)
    assert state["text"] == "цитата"
    assert state["mode"] == "quote"
    assert called == [(msg.edit_text, 4242)]


# ---------- save_new_wing ----------


def test_save_new_wing(monkeypatch):
    _enable(monkeypatch)
    sh.fsm.update_data(4242, _save_state={"wing": "", "room": None})
    called = []

    async def fake_rooms(edit_func, uid):
        called.append((edit_func, uid))

    async def fake_subprocess(*a, **k):
        return SimpleNamespace(communicate=lambda: asyncio.sleep(0))

    monkeypatch.setattr("handlers.palace._show_save_rooms", fake_rooms)
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess)
    sh._pending_mcp_input[4242] = "save_new_wing"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "Новое крыло", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert sh._save_state.get(4242)["wing"] == "новое_крыло"
    assert called == [(msg.edit_text, 4242)]


def test_save_new_wing_subprocess_error(monkeypatch):
    _enable(monkeypatch)

    async def boom(*a, **k):
        raise RuntimeError("proc fail")

    async def fake_rooms(edit_func, uid):
        return None

    monkeypatch.setattr("handlers.palace._show_save_rooms", fake_rooms)
    monkeypatch.setattr("asyncio.create_subprocess_exec", boom)
    sh._pending_mcp_input[4242] = "save_new_wing"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "крыло", FakeAnswerFactory(msg),
    ))
    assert result is True


# ---------- save_new_room ----------


def test_save_new_room(monkeypatch):
    _enable(monkeypatch)
    sh.fsm.update_data(4242, _save_state={"wing": "w", "room": None})
    called = []

    async def fake_confirm(edit_func, uid):
        called.append((edit_func, uid))

    monkeypatch.setattr("handlers.palace._save_confirm", fake_confirm)
    sh._pending_mcp_input[4242] = "save_new_room"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "Комната снов", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert sh._save_state.get(4242)["room"] == "Комната_снов"
    assert called == [(msg.edit_text, 4242)]


# ---------- pn_new_wing / pn_new_room ----------


def test_pn_new_wing_success(monkeypatch):
    _enable(monkeypatch)
    from handlers import personal_note as pn_mod

    pn_mod._note_data[4242] = {"text": "заметка", "wing": "", "taxonomy": {}}
    shown = []

    async def fake_rooms(uid, edit_func):
        shown.append((uid, edit_func))

    async def fake_subprocess(*a, **k):
        return SimpleNamespace(communicate=lambda: asyncio.sleep(0))

    monkeypatch.setattr("handlers.personal_note._show_pn_rooms", fake_rooms)
    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess)
    sh._pending_mcp_input[4242] = "pn_new_wing"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "Философия", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert pn_mod._note_data[4242]["wing"] == "философия"
    assert shown == [(4242, msg.edit_text)]
    pn_mod._note_data.pop(4242, None)


def test_pn_new_wing_subprocess_error(monkeypatch):
    _enable(monkeypatch)
    from handlers import personal_note as pn_mod

    pn_mod._note_data[4242] = {"text": "заметка", "wing": "", "taxonomy": {}}
    shown = []

    async def fake_rooms(uid, edit_func):
        shown.append((uid, edit_func))

    async def boom(*a, **k):
        raise RuntimeError("proc fail")

    monkeypatch.setattr("handlers.personal_note._show_pn_rooms", fake_rooms)
    monkeypatch.setattr("asyncio.create_subprocess_exec", boom)
    sh._pending_mcp_input[4242] = "pn_new_wing"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "крыло", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert pn_mod._note_data[4242]["wing"] == "крыло"
    assert shown == [(4242, msg.edit_text)]
    pn_mod._note_data.pop(4242, None)


def test_pn_new_wing_empty_input(monkeypatch):
    _enable(monkeypatch)
    from handlers import personal_note as pn_mod

    pn_mod._note_data[4242] = {"text": "заметка", "wing": "", "taxonomy": {}}
    called = []

    async def fake_subprocess(*a, **k):
        called.append(a)
        return SimpleNamespace(communicate=lambda: asyncio.sleep(0))

    monkeypatch.setattr("asyncio.create_subprocess_exec", fake_subprocess)
    sh._pending_mcp_input[4242] = "pn_new_wing"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "   ", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert called == []
    assert "Название не может быть пустым" in msg.edits[-1][0]
    pn_mod._note_data.pop(4242, None)


def test_pn_new_room_success(monkeypatch):
    _enable(monkeypatch)
    from handlers import personal_note as pn_mod

    pn_mod._note_data[4242] = {"text": "заметка", "wing": "w", "room": ""}
    shown = []

    async def fake_confirm(uid, edit_func):
        shown.append((uid, edit_func))

    monkeypatch.setattr("handlers.personal_note._show_pn_confirm", fake_confirm)
    sh._pending_mcp_input[4242] = "pn_new_room"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "Комната снов", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert pn_mod._note_data[4242]["room"] == "Комната снов"
    assert shown == [(4242, msg.edit_text)]
    pn_mod._note_data.pop(4242, None)


def test_pn_new_room_empty_input(monkeypatch):
    _enable(monkeypatch)
    from handlers import personal_note as pn_mod

    pn_mod._note_data[4242] = {"text": "заметка", "wing": "w", "room": ""}
    sh._pending_mcp_input[4242] = "pn_new_room"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "  ", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert "Название не может быть пустым" in msg.edits[-1][0]
    assert pn_mod._note_data[4242]["room"] == ""
    pn_mod._note_data.pop(4242, None)


def test_kg_add_subject(monkeypatch):
    _enable(monkeypatch)
    sh._pending_mcp_input[4242] = "kg_add_subject"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "Шопенгауэр", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert sh._kg_add_state.get(4242)["subject"] == "Шопенгауэр"
    text, kwargs = msg.edits[-1]
    assert "Шопенгауэр" in text
    data = _kb_data(kwargs["reply_markup"])
    assert data[0] == f"p_kga_pr:{sh.KG_PREDICATES[0][0]}"
    assert data[-1] == "p_kga_x"


def test_kg_add_full_flow(monkeypatch):
    """Полный флоу добавления факта без ручного создания state — регрессия бага
    «Сессия истекла» на шаге ввода объекта."""
    _enable(monkeypatch)
    mcp = FakeMCPSeq(["✅ факт"])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    monkeypatch.setattr("handlers.palace.kg.get_mcp", lambda: mcp)
    captured = {}
    _capture_finalize(monkeypatch, captured)

    cb_start = FakeCb(data="p_kga")
    asyncio.run(palace.kg.cb_kg_add_start(cb_start))
    assert sh._kg_add_state[4242] == {"subject": "", "predicate": "", "object": ""}

    msg = FakeAnswerMsg()
    asyncio.run(palace.process_mcp_text_input(
        4242, "Шопенгауэр", FakeAnswerFactory(msg),
    ))
    assert sh._kg_add_state.get(4242)["subject"] == "Шопенгауэр"

    cb_pred = FakeCb(data="p_kga_pr:influenced_by")
    asyncio.run(palace.kg.cb_kg_add_predicate_chosen(cb_pred))
    assert sh._kg_add_state.get(4242)["predicate"] == "influenced_by"
    assert sh._pending_mcp_input[4242] == "kg_add_object"

    msg2 = FakeAnswerMsg()
    asyncio.run(palace.process_mcp_text_input(
        4242, "Кант", FakeAnswerFactory(msg2),
    ))
    assert sh._kg_add_state.get(4242)["object"] == "Кант"

    cb_confirm = FakeCb(data="p_kga_c")
    asyncio.run(palace.kg.cb_kg_add_confirm(cb_confirm))
    assert mcp.calls[0] == (
        "mempalace_kg_add",
        {"subject": "Шопенгауэр", "predicate": "influenced_by", "object": "Кант"},
    )
    assert captured["text"] == "✅ факт"
    assert captured["ctx"] == {"parent_cb": "p_kg"}
    assert 4242 not in sh._kg_add_state


# ---------- kg_add_object ----------


def test_kg_add_object(monkeypatch):
    _enable(monkeypatch)
    sh.fsm.update_data(4242, _kg_add_state={
        "subject": "Шопенгауэр", "predicate": "influenced_by",
    })
    sh._pending_mcp_input[4242] = "kg_add_object"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "Кант", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert sh._kg_add_state.get(4242)["object"] == "Кант"
    text, kwargs = msg.edits[-1]
    assert "Шопенгауэр" in text
    assert "Кант" in text
    assert _kb_data(kwargs["reply_markup"]) == ["p_kga_c", "p_kga_x"]


def test_kg_add_object_no_state(monkeypatch):
    _enable(monkeypatch)
    sh._pending_mcp_input[4242] = "kg_add_object"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "Кант", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert msg.edits[-1][0] == "❌ Сессия истекла."


# ---------- fallback save_state / fsm pop+clear ----------


def test_fallback_save_state_to_save_new_room(monkeypatch):
    _enable(monkeypatch)
    sh.fsm.update_data(4242, _save_state={"wing": "w", "room": None})
    called = []

    async def fake_confirm(edit_func, uid):
        called.append((edit_func, uid))

    monkeypatch.setattr("handlers.palace._save_confirm", fake_confirm)
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "Комната", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert sh._save_state.get(4242)["room"] == "Комната"
    assert called == [(msg.edit_text, 4242)]


def test_fsm_pop_and_clear_when_state_not_idle(monkeypatch):
    _enable(monkeypatch)
    from services.conversation_fsm import ConversationState

    sh.fsm.set_state(4242, ConversationState.MCP_INPUT)
    sh.fsm.update_data(4242, _pending_mcp_input="save_quote")
    sh._save_state[4242] = {"wing": "w", "room": "r"}
    called = []

    async def fake_wings(edit_func, uid):
        called.append((edit_func, uid))

    monkeypatch.setattr("handlers.palace._show_save_wings", fake_wings)
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: FakeMCPSeq([]))
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "цитата", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert sh.fsm.get_state(4242) == ConversationState.IDLE
    assert sh.fsm.get_data(4242).get("_pending_mcp_input") is None
    assert called == [(msg.edit_text, 4242)]


# ---------- traverse extra branches ----------


def test_traverse_digit_room(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"error": "Комната не найдена"})])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    sh._pending_mcp_input[4242] = "traverse"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "5", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert mcp.calls[0][1] == {"start_room": "", "max_hops": 2}
    assert "Комната не найдена" in msg.edits[-1][0]


def test_traverse_digit_hops_and_room(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps([])])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    sh._pending_mcp_input[4242] = "traverse"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "3 2", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert mcp.calls[0][1] == {"start_room": "2", "max_hops": 3}


# ---------- save branches without state ----------


def test_save_quote_no_state(monkeypatch):
    _enable(monkeypatch)
    called = []

    async def fake_wings(edit_func, uid):
        called.append((edit_func, uid))

    monkeypatch.setattr("handlers.palace._show_save_wings", fake_wings)
    sh._pending_mcp_input[4242] = "save_quote"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "цитата", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert called == [(msg.edit_text, 4242)]


def test_save_new_room_no_state(monkeypatch):
    _enable(monkeypatch)
    called = []

    async def fake_confirm(edit_func, uid):
        called.append((edit_func, uid))

    monkeypatch.setattr("handlers.palace._save_confirm", fake_confirm)
    sh._pending_mcp_input[4242] = "save_new_room"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "Комната", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert called == [(msg.edit_text, 4242)]


def test_kg_add_subject_no_state(monkeypatch):
    _enable(monkeypatch)
    sh._pending_mcp_input[4242] = "kg_add_subject"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "Шопенгауэр", FakeAnswerFactory(msg),
    ))
    assert result is True
    text, kwargs = msg.edits[-1]
    assert "тип связи" in text
    assert _kb_data(kwargs["reply_markup"])[0] == f"p_kga_pr:{palace.KG_PREDICATES[0][0]}"


# ---------- kg_query ----------


def test_kg_query_no_facts(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps([])])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    sh._pending_mcp_input[4242] = "kg_query"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "Кант", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert mcp.calls[0][1] == {"entity": "кант", "direction": "both"}
    text, kwargs = msg.edits[-1]
    assert "Нет фактов в графе знаний." in text
    assert _kb_data(kwargs["reply_markup"]) == ["p_kgrs:кант"]


def test_kg_query_with_facts(monkeypatch):
    _enable(monkeypatch)
    facts = [{"subject": "кант", "predicate": "влияет_на", "object": "гегель",
              "direction": "out", "strength": 2}]
    mcp = FakeMCPSeq([json.dumps({"facts": facts})])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    captured = {}

    async def fake_send_page(uid, edit_func):
        captured["uid"] = uid
        captured["edit_func"] = edit_func

    monkeypatch.setattr("handlers.palace._send_kg_page", fake_send_page)
    sh._pending_mcp_input[4242] = "kg_query"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "Кант", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert captured["uid"] == 4242
    assert captured["edit_func"] == msg.edit_text
    data = sh._kg_page_data.get(4242)
    assert data["entity"] == "кант"
    assert data["facts"] == facts
    assert data["page"] == 0


# ---------- find_tunnels ----------


def test_find_tunnels_none(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([None])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    sh._pending_mcp_input[4242] = "find_tunnels"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "math", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert mcp.calls[0][1] == {"wing_a": "math"}
    assert "Туннелей между этими крыльями не найдено." in msg.edits[-1][0]


def test_find_tunnels_found(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps([
        {"room": "интегралы", "wings": ["math", "physics"], "count": 5},
    ])])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    sh._pending_mcp_input[4242] = "find_tunnels"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "math physics", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert mcp.calls[0][1] == {"wing_a": "math_physics"}
    assert "Найдено туннелей: 1" in captured["text"]
    assert captured["ctx"] == {"parent_cb": "p_tun"}


# ---------- follow_tunnels ----------


def test_follow_tunnels_short(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: FakeMCPSeq([]))
    sh._pending_mcp_input[4242] = "follow_tunnels"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "только", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert "Укажите крыло и комнату" in msg.edits[-1][0]


def test_follow_tunnels_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq(["✅ туннели: a/b"])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    sh._pending_mcp_input[4242] = "follow_tunnels"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "мои заметки сны", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert mcp.calls[0][1] == {"wing": "мои", "room": "заметки_сны"}
    assert captured["text"] == "✅ туннели: a/b"
    assert captured["ctx"] == {"wing": "мои", "room": "заметки_сны", "parent_cb": "p_tun"}


# ---------- create_tunnel ----------


def test_create_tunnel_no_state(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: FakeMCPSeq([]))
    sh._pending_mcp_input[4242] = "create_tunnel"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "метка", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert "Сессия создания туннеля истекла" in msg.edits[-1][0]


def test_create_tunnel_with_label(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnel_id": "t1"})])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    sh._create_tunnel_state[4242] = {
        "source_wing": "a", "source_room": "r1",
        "target_wing": "b", "target_room": "r2",
    }
    sh._pending_mcp_input[4242] = "create_tunnel"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "связаны", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert mcp.calls[0][1]["label"] == "связаны"
    assert "Туннель создан!" in captured["text"]
    assert "Описание: связаны" in captured["text"]
    assert "ID: t1" in captured["text"]
    assert captured["ctx"] == {
        "source_wing": "a", "target_wing": "b", "parent_cb": "p_tun",
    }
    assert sh._create_tunnel_state.get(4242) is None


def test_create_tunnel_dash_label(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnel_id": ""})])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    sh._create_tunnel_state[4242] = {
        "source_wing": "a", "source_room": "r1",
        "target_wing": "b", "target_room": "r2",
    }
    sh._pending_mcp_input[4242] = "create_tunnel"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "-", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert "label" not in mcp.calls[0][1]
    assert "Описание:" not in captured["text"]


def test_create_tunnel_bad_json(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq(["сырой ответ"])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    sh._create_tunnel_state[4242] = {
        "source_wing": "a", "source_room": "r1",
        "target_wing": "b", "target_room": "r2",
    }
    sh._pending_mcp_input[4242] = "create_tunnel"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "метка", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert captured["text"] == "сырой ответ"


# ---------- ask_room_ai ----------


def test_ask_room_ai(monkeypatch):
    _enable(monkeypatch)
    called = []

    async def fake_answer(msg, uid, wing, room, question, with_web=False):
        called.append((msg, uid, wing, room, question))

    monkeypatch.setattr("handlers.palace.navigation._answer_room_ai", fake_answer)
    sh._pending_mcp_input[4242] = "ask_room_ai:math:integral"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, " что это? ", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert called == [(msg, 4242, "math", "integral", "что это?")]


# ---------- tunnel_discuss ----------


def test_tunnel_discuss_no_ctx(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: FakeMCPSeq([]))
    sh._pending_mcp_input[4242] = "tunnel_discuss"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "почему?", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert "Сессия обсуждения туннеля истекла." in msg.edits[-1][0]


def test_tunnel_discuss_not_found(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": [
        {"id": "t2", "source": {"wing": "a", "room": "r"},
         "target": {"wing": "b", "room": "r"}, "label": ""},
    ]})])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    sh._user_context[4242] = {"tunnel_id": "t9"}
    sh._pending_mcp_input[4242] = "tunnel_discuss"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "почему?", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert "Туннель не найден." in msg.edits[-1][0]


def test_tunnel_discuss_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        json.dumps([
            {"id": "t1",
             "source": {"wing": "a", "room": "r1"},
             "target": {"wing": "b", "room": "r2"},
             "label": "связь"},
        ]),
        "содержимое a/r1",
        "содержимое b/r2",
    ])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    monkeypatch.setattr(
        "handlers.palace.get_current_ai", lambda: ("test-engine", "test-model"),
    )
    monkeypatch.setattr(
        "services.ai_engine._sync_ai_call",
        lambda engine, model, messages: "иИ-ответ",
    )
    captured = {}
    _capture_finalize(monkeypatch, captured)
    sh._user_context[4242] = {"tunnel_id": "t1"}
    sh._pending_mcp_input[4242] = "tunnel_discuss"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "почему?", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert captured["text"] == "иИ-ответ"
    assert "🤖 Анализ туннеля" in captured["title"]
    assert captured["ctx"] == {"parent_cb": "p_tun"}
    assert [c[0] for c in mcp.calls] == [
        "mempalace_list_tunnels", "mempalace_read_drawer", "mempalace_read_drawer",
    ]


def test_tunnel_discuss_read_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        json.dumps([{"id": "t1",
                     "source": {"wing": "a", "room": "r1"},
                     "target": {"wing": "b", "room": "r2"},
                     "label": ""}]),
        RuntimeError("read failed"),
        "содержимое",
    ])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    monkeypatch.setattr(
        "handlers.palace.get_current_ai", lambda: ("e", "m"),
    )
    monkeypatch.setattr(
        "services.ai_engine._sync_ai_call",
        lambda engine, model, messages: "ответ",
    )
    captured = {}
    _capture_finalize(monkeypatch, captured)
    sh._user_context[4242] = {"tunnel_id": "t1"}
    sh._pending_mcp_input[4242] = "tunnel_discuss"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "почему?", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert captured["text"] == "ответ"


def test_tunnel_discuss_ai_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        json.dumps([{"id": "t1",
                     "source": {"wing": "a", "room": "r1"},
                     "target": {"wing": "b", "room": "r2"},
                     "label": ""}]),
        "содержимое",
        "содержимое",
    ])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    monkeypatch.setattr(
        "handlers.palace.get_current_ai", lambda: ("e", "m"),
    )
    monkeypatch.setattr(
        "services.ai_engine._sync_ai_call",
        lambda engine, model, messages: (_ for _ in ()).throw(RuntimeError("ai down")),
    )
    sh._user_context[4242] = {"tunnel_id": "t1"}
    sh._pending_mcp_input[4242] = "tunnel_discuss"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "почему?", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert "Ошибка ИИ: ai down" in msg.edits[-1][0]


# ---------- top-level exception ----------


def test_process_mcp_text_input_mcp_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("mcp boom")])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    sh._pending_mcp_input[4242] = "list_rooms"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "*", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert msg.edits[-1][0] == "❌ Ошибка: mcp boom"


# ---------- remaining partial arcs ----------


def test_find_tunnels_empty_query(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([None])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    sh._pending_mcp_input[4242] = "find_tunnels"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "   ", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert mcp.calls[0][1] == {}
    assert "Туннелей между этими крыльями не найдено." in msg.edits[-1][0]


def test_find_tunnels_two_wing_query(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([None])
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: mcp)
    sh._pending_mcp_input[4242] = "find_tunnels"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "math\nphysics", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert mcp.calls[0][1] == {"wing_a": "math", "wing_b": "physics"}


def test_ask_room_ai_short_action(monkeypatch):
    _enable(monkeypatch)
    sh._pending_mcp_input[4242] = "ask_room_ai:wing"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "вопрос", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert msg.edits == []


def test_unknown_action_falls_through(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr("handlers.palace.get_mcp", lambda: FakeMCPSeq([]))
    sh._pending_mcp_input[4242] = "unknown_action"
    msg = FakeAnswerMsg()
    result = asyncio.run(palace.process_mcp_text_input(
        4242, "x", FakeAnswerFactory(msg),
    ))
    assert result is True
    assert msg.edits == []
