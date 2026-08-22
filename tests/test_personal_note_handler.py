"""Unit tests for handlers.personal_note."""

from types import SimpleNamespace

import pytest

from handlers import personal_note as pn


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=4242, text=""):
        self.from_user = FakeUser(uid)
        self.text = text
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

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.message.edits.append((text, parse_mode, reply_markup))


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


def _enable(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    monkeypatch.setattr(pn, "safe_html_format", lambda t: t)


def _async_result(value):
    async def _inner(*a, **kw):
        return value

    return _inner


@pytest.fixture(autouse=True)
def _clean_state():
    pn._whisper = None
    pn._waiting_for_note.clear()
    pn._note_data.clear()
    pn._list_state.clear()
    pn._active_drawer.clear()
    pn._quote_waiting.clear()
    yield
    pn._whisper = None
    pn._waiting_for_note.clear()
    pn._note_data.clear()
    pn._list_state.clear()
    pn._active_drawer.clear()
    pn._quote_waiting.clear()
    from handlers.palace.save import _save_state

    _save_state.pop(4242, None)
    from handlers.palace.shared import _pending_mcp_input

    _pending_mcp_input.pop(4242, None)


def _markup_data(msg, idx=-1):
    kb = msg.edits[idx][2] or msg.answers[idx][2]
    if kb is None:
        return []
    return [b.callback_data for row in kb.inline_keyboard for b in row]


# ---------- get_whisper ----------


def test_get_whisper_creates_once(monkeypatch):
    _enable(monkeypatch)
    created = []

    def fake_factory(*a, **kw):
        created.append(a)
        return SimpleNamespace()

    monkeypatch.setattr(pn, "WhisperModel", fake_factory)
    first = pn.get_whisper()
    second = pn.get_whisper()
    assert first is second
    assert len(created) == 1


def test_get_whisper_uses_existing(monkeypatch):
    _enable(monkeypatch)
    fake = SimpleNamespace()
    pn._whisper = fake
    assert pn.get_whisper() is fake


# ---------- _transcribe_sync ----------


def test_transcribe_sync_success(monkeypatch):
    _enable(monkeypatch)
    exported = []

    class FakeSeg:
        def export(self, path, format=None):
            exported.append((path, format))

    seg = FakeSeg()

    def fake_from_ogg(path):
        return seg

    monkeypatch.setattr(pn.pydub.AudioSegment, "from_ogg", fake_from_ogg)
    fake_whisper = SimpleNamespace(
        transcribe=lambda path, language, beam_size: (
            iter([SimpleNamespace(text="привет"), SimpleNamespace(text="мир")]),
            None,
        ),
    )
    monkeypatch.setattr(pn, "get_whisper", lambda: fake_whisper)
    result = pn._transcribe_sync("a.ogg", "b.wav")
    assert result == "привет мир"
    assert exported == [("b.wav", "wav")]


def test_transcribe_sync_empty(monkeypatch):
    _enable(monkeypatch)

    class FakeSeg:
        def export(self, path, format=None):
            pass

    monkeypatch.setattr(
        pn.pydub.AudioSegment, "from_ogg", lambda path: FakeSeg(),
    )
    fake_whisper = SimpleNamespace(
        transcribe=lambda path, language, beam_size: (iter([]), None),
    )
    monkeypatch.setattr(pn, "get_whisper", lambda: fake_whisper)
    assert pn._transcribe_sync("a.ogg", "b.wav") == ""


# ---------- _taxonomy_for_prompt ----------


def test_taxonomy_for_prompt_dict_rooms():
    tax = {"крыло1": {"a": {}, "b": {}}, "крыло2": {"c": {}}}
    text = pn._taxonomy_for_prompt(tax)
    assert "- крыло1: a, b" in text
    assert "- крыло2: c" in text


def test_taxonomy_for_prompt_non_dict_rooms():
    text = pn._taxonomy_for_prompt({"крыло": ["a", "b"]})
    assert "- крыло: " in text
    assert "a" not in text


def test_taxonomy_for_prompt_empty():
    assert pn._taxonomy_for_prompt({}) == ""


# ---------- _format_note ----------


def test_format_note_success(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(pn, "get_current_ai", lambda: ("ollama", "qwen2.5:7b"))
    seen = {}

    async def fake_ai(engine, model, msgs):
        seen["engine"] = engine
        seen["model"] = model
        seen["msgs"] = msgs
        return "отформатировано"

    monkeypatch.setattr(pn, "get_ai_response_async", fake_ai)
    import asyncio

    out = asyncio.run(pn._format_note("сырой текст"))
    assert out == "отформатировано"
    assert seen["engine"] == "ollama"
    assert seen["model"] == "qwen2.5:7b"
    assert seen["msgs"][0]["content"] == pn.FORMAT_PROMPT
    assert seen["msgs"][1]["content"] == "сырой текст"


# ---------- _classify_note ----------


def test_classify_note_plain_json(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(pn, "get_current_ai", lambda: ("ollama", "m"))
    monkeypatch.setattr(
        pn, "get_ai_response_async",
        _async_result('{"wing": "w", "room": "r", "reason": "rr"}'),
    )
    import asyncio

    out = asyncio.run(pn._classify_note("текст", {"w": {}}))
    assert out == {"wing": "w", "room": "r", "reason": "rr"}


def test_classify_note_fenced_json(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(pn, "get_current_ai", lambda: ("ollama", "m"))
    monkeypatch.setattr(
        pn, "get_ai_response_async",
        _async_result('```json\n{"wing": "w"}\n```'),
    )
    import asyncio

    out = asyncio.run(pn._classify_note("текст", {}))
    assert out == {"wing": "w"}


def test_classify_note_invalid_json_fallback(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(pn, "get_current_ai", lambda: ("ollama", "m"))
    monkeypatch.setattr(
        pn, "get_ai_response_async", _async_result("не json"),
    )
    import asyncio

    out = asyncio.run(pn._classify_note("текст", {}))
    assert out == {
        "wing": "личные_мысли",
        "room": "inbox",
        "reason": "автоопределение не удалось",
    }


def test_classify_note_none_fallback(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(pn, "get_current_ai", lambda: ("ollama", "m"))
    monkeypatch.setattr(pn, "get_ai_response_async", _async_result(None))
    import asyncio

    out = asyncio.run(pn._classify_note("текст", {}))
    assert out["wing"] == "личные_мысли"


# ---------- process_note_input ----------


def test_process_note_input_success(monkeypatch):
    _enable(monkeypatch)
    pn._waiting_for_note[4242] = True
    mcp = FakeMCP('{"taxonomy": {"крыло": {"комната": {}}}}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    monkeypatch.setattr(pn, "_format_note", _async_result("отформатированный"))
    monkeypatch.setattr(
        pn, "_classify_note",
        _async_result({"wing": "крыло", "room": "комната", "reason": "причина"}),
    )
    msg = FakeMessage()
    import asyncio

    asyncio.run(pn.process_note_input(4242, "сыро", msg.answer))
    assert 4242 not in pn._waiting_for_note
    assert msg.answers[0] == ("✍️ Форматирую...", None, None)
    assert msg.edits[0] == ("🔍 Определяю тематику...", None, None)
    preview = msg.edits[1][0]
    assert "отформатированный" in preview
    assert "Сохранить?" in preview
    assert "причина" in preview
    assert "pn_cf" in _markup_data(msg, idx=1)
    assert pn._note_data[4242]["wing"] == "крыло"
    assert pn._note_data[4242]["raw"] == "сыро"
    assert pn._note_data[4242]["taxonomy"] == {"крыло": {"комната": {}}}
    assert mcp.calls == [("mempalace_get_taxonomy", None)]


def test_process_note_input_no_taxonomy_key(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"other": 1}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    monkeypatch.setattr(pn, "_format_note", _async_result("текст"))
    monkeypatch.setattr(
        pn, "_classify_note",
        _async_result({"wing": "личные_мысли", "room": "inbox"}),
    )
    msg = FakeMessage()
    import asyncio

    asyncio.run(pn.process_note_input(4242, "сыро", msg.answer))
    assert pn._note_data[4242]["taxonomy"] == {}


def test_process_note_input_error(monkeypatch):
    _enable(monkeypatch)

    async def boom(raw_text):
        raise RuntimeError("ai упал")

    monkeypatch.setattr(pn, "_format_note", boom)
    msg = FakeMessage()
    import asyncio

    asyncio.run(pn.process_note_input(4242, "сыро", msg.answer))
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in msg.edits[0][0]


def test_process_note_input_error_edit_fails_too(monkeypatch):
    _enable(monkeypatch)

    async def boom(raw_text):
        raise RuntimeError("x")

    monkeypatch.setattr(pn, "_format_note", boom)

    class BrokenMsg(FakeMessage):
        async def edit_text(self, text, parse_mode=None, reply_markup=None):
            raise RuntimeError("edit fail")

    msg = BrokenMsg()
    import asyncio

    asyncio.run(pn.process_note_input(4242, "сыро", msg.answer))
    assert msg.answers[0] == ("✍️ Форматирую...", None, None)


# ---------- cmd_personal_note ----------


def test_cmd_personal_note_allowed(monkeypatch):
    _enable(monkeypatch)
    msg = FakeMessage()
    import asyncio

    asyncio.run(pn.cmd_personal_note(msg))
    assert pn._waiting_for_note[4242] is True
    assert "Личная заметка" in msg.answers[0][0]
    assert msg.answers[0][1] == "HTML"
    assert msg.answers[0][2] is not None


def test_cmd_personal_note_not_allowed(monkeypatch):
    _enable(monkeypatch)
    msg = FakeMessage(uid=999)
    import asyncio

    asyncio.run(pn.cmd_personal_note(msg))
    assert msg.answers == []
    assert 999 not in pn._waiting_for_note


# ---------- cb_pn_save ----------


def test_cb_pn_save_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="pn_cf")
    import asyncio

    asyncio.run(pn.cb_pn_save(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла."


def test_cb_pn_save_success_personal(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {
        "text": "заметка",
        "wing": "личные_мысли",
        "room": "inbox",
    }
    mcp = FakeMCP('{"ok": true}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_cf")
    import asyncio

    asyncio.run(pn.cb_pn_save(cb))
    assert len(mcp.calls) == 1
    assert mcp.calls[0][0] == "mempalace_add_drawer"
    assert mcp.calls[0][1]["source_file"] == "personal_note"
    final = cb.message.edits[-1][0]
    assert "Сохранено!" in final
    assert "личные_мысли/inbox" in final
    assert "копия" not in final


def test_cb_pn_save_success_copy_to_personal(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {
        "text": "заметка",
        "wing": "крыло",
        "room": "комната",
    }
    mcp = FakeMCP('{"ok": true}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_cf")
    import asyncio

    asyncio.run(pn.cb_pn_save(cb))
    assert len(mcp.calls) == 2
    assert mcp.calls[1][1]["wing"] == "личные_мысли"
    assert mcp.calls[1][1]["room"] == "inbox"
    final = cb.message.edits[-1][0]
    assert "копия в" in final


def test_cb_pn_save_invalid_json(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {"text": "x", "wing": "w", "room": "r"}
    mcp = FakeMCP("не json")
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_cf")
    import asyncio

    asyncio.run(pn.cb_pn_save(cb))
    assert "❌ Ошибка:" in cb.message.edits[-1][0]


def test_cb_pn_save_mcp_error(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {"text": "x", "wing": "w", "room": "r"}
    mcp = FakeMCP(fail_on="mcp упал")
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_cf")
    import asyncio

    asyncio.run(pn.cb_pn_save(cb))
    assert "❌ Ошибка: mcp упал" in cb.message.edits[-1][0]


def test_cb_pn_wing_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data=None)
    import asyncio

    asyncio.run(pn.cb_pn_wing(cb))
    assert cb.message.edits == []


# ---------- cb_pn_room ----------


def test_cb_pn_room_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="pn_room:0")
    import asyncio

    asyncio.run(pn.cb_pn_room(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла."


def test_cb_pn_room_no_callback_data(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {"text": "x"}
    cb = FakeCb(data=None)
    import asyncio

    asyncio.run(pn.cb_pn_room(cb))
    assert cb.message.edits == []


def test_cb_pn_room_new_inbox(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {"text": "заметка", "wing": "крыло"}
    cb = FakeCb(data="pn_room:-1")
    import asyncio

    asyncio.run(pn.cb_pn_room(cb))
    assert pn._note_data[4242]["room"] == "inbox"
    preview = cb.message.edits[-1][0]
    assert "крыло/inbox" in preview
    assert "Сохранить?" in preview
    assert "pn_cf" in _markup_data(cb.message)


def test_cb_pn_room_valid_index(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {
        "text": "заметка", "wing": "крыло", "room_list": ["r1", "r2"],
    }
    cb = FakeCb(data="pn_room:1")
    import asyncio

    asyncio.run(pn.cb_pn_room(cb))
    assert pn._note_data[4242]["room"] == "r2"


def test_cb_pn_room_out_of_range(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {
        "text": "x", "wing": "крыло", "room_list": ["r1"],
    }
    cb = FakeCb(data="pn_room:99")
    import asyncio

    asyncio.run(pn.cb_pn_room(cb))
    assert pn._note_data[4242]["room"] == "inbox"


def test_cb_pn_room_malformed_index(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {"text": "x", "wing": "крыло", "room_list": ["r1"]}
    cb = FakeCb(data="pn_room:abc")
    import asyncio

    asyncio.run(pn.cb_pn_room(cb))
    assert pn._note_data[4242]["room"] == "inbox"


def test_cb_pn_room_empty_room_list(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {"text": "x", "wing": "крыло", "room_list": []}
    cb = FakeCb(data="pn_room:0")
    import asyncio

    asyncio.run(pn.cb_pn_room(cb))
    assert pn._note_data[4242]["room"] == "inbox"


# ---------- создание крыла/комнаты при сохранении ----------


def test_cb_pn_reclass_has_new_wing_button(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {
        "text": "заметка",
        "taxonomy": {"личные_мысли": {"inbox": 0}, "крыло": {"комната": 0}},
    }
    cb = FakeCb(data="pn_reclass")
    import asyncio

    asyncio.run(pn.cb_pn_reclass(cb))
    data = _markup_data(cb.message)
    assert "pn_wing_new" in data
    assert data[-1] == "pn_cancel"


def test_cb_pn_wing_new(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {"text": "заметка"}
    cb = FakeCb(data="pn_wing_new")
    import asyncio

    asyncio.run(pn.cb_pn_wing_new(cb))
    from handlers.palace.shared import _pending_mcp_input

    assert _pending_mcp_input[4242] == "pn_new_wing"
    assert pn._note_data[4242]["creating"] is True
    assert "Введите название нового крыла" in cb.message.edits[-1][0]


def test_cb_pn_wing_new_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="pn_wing_new")
    import asyncio

    asyncio.run(pn.cb_pn_wing_new(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла."


def test_cb_pn_room_new(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {"text": "заметка"}
    cb = FakeCb(data="pn_room_new")
    import asyncio

    asyncio.run(pn.cb_pn_room_new(cb))
    from handlers.palace.shared import _pending_mcp_input

    assert _pending_mcp_input[4242] == "pn_new_room"
    assert pn._note_data[4242]["creating"] is True
    assert "Введите название новой комнаты" in cb.message.edits[-1][0]


def test_cb_pn_room_new_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="pn_room_new")
    import asyncio

    asyncio.run(pn.cb_pn_room_new(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла."


def test_show_pn_rooms_has_new_room_button(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {
        "text": "x", "wing": "новое_крыло",
        "taxonomy": {"новое_крыло": {}},
    }
    edits = []

    async def edit_func(text, **kwargs):
        edits.append((text, kwargs))

    import asyncio

    asyncio.run(pn._show_pn_rooms(4242, edit_func))
    assert "inbox" in pn._note_data[4242]["room_list"]
    data = [b.callback_data for row in edits[-1][1]["reply_markup"].inline_keyboard for b in row]
    assert "pn_room_new" in data
    assert "pn_room:-1" in data
    assert "pn_reclass" in data


def test_show_pn_rooms_no_data(monkeypatch):
    _enable(monkeypatch)
    edits = []

    async def edit_func(text, **kwargs):
        edits.append(text)

    import asyncio

    asyncio.run(pn._show_pn_rooms(4242, edit_func))
    assert edits == ["❌ Сессия истекла."]


def test_show_pn_confirm_no_data(monkeypatch):
    _enable(monkeypatch)
    edits = []

    async def edit_func(text, **kwargs):
        edits.append(text)

    import asyncio

    asyncio.run(pn._show_pn_confirm(4242, edit_func))
    assert edits == ["❌ Сессия истекла."]


# ---------- cb_pn_cancel / cmd_cancel_note ----------


def test_cb_pn_cancel(monkeypatch):
    _enable(monkeypatch)
    pn._note_data[4242] = {"text": "x"}
    pn._waiting_for_note[4242] = True
    cb = FakeCb(data="pn_cancel")
    import asyncio

    asyncio.run(pn.cb_pn_cancel(cb))
    assert cb.message.edits[-1][0] == "❌ Отменено."
    assert 4242 not in pn._note_data
    assert 4242 not in pn._waiting_for_note


def test_cmd_cancel_note(monkeypatch):
    _enable(monkeypatch)
    called = []

    async def fake_menu(m):
        called.append(m)

    monkeypatch.setattr(pn, "go_main_menu", fake_menu)
    pn._note_data[4242] = {"text": "x"}
    pn._waiting_for_note[4242] = True
    msg = FakeMessage(text="❌ Отмена")
    import asyncio

    asyncio.run(pn.cmd_cancel_note(msg))
    assert called == [msg]
    assert 4242 not in pn._note_data
    assert 4242 not in pn._waiting_for_note


def test_cmd_cancel_note_not_allowed(monkeypatch):
    _enable(monkeypatch)
    called = []

    async def fake_menu(m):
        called.append(m)

    monkeypatch.setattr(pn, "go_main_menu", fake_menu)
    msg = FakeMessage(uid=999, text="❌ Отмена")
    import asyncio

    asyncio.run(pn.cmd_cancel_note(msg))
    assert called == []


# ---------- cmd_list_personal_notes / _show_pn_page ----------


def test_cmd_list_personal_notes_allowed(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    msg = FakeMessage(text="📖 Личные мысли")
    import asyncio

    asyncio.run(pn.cmd_list_personal_notes(msg))
    assert "Пока нет личных заметок" in msg.answers[0][0]
    assert mcp.calls[0] == (
        "mempalace_list_drawers",
        {"wing": "личные_мысли", "room": "inbox", "limit": 5, "offset": 0},
    )


def test_cmd_list_personal_notes_not_allowed(monkeypatch):
    _enable(monkeypatch)
    msg = FakeMessage(uid=999, text="📖 Личные мысли")
    import asyncio

    asyncio.run(pn.cmd_list_personal_notes(msg))
    assert msg.answers == []


def test_show_pn_page_with_drawers(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(
        '{"drawers": [{"content_preview": "первая"}, {"content": "вторая длинная"}], '
        '"count": 7}',
    )
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    msg = FakeMessage()
    import asyncio

    asyncio.run(
        pn._show_pn_page(msg, msg.answer, wing="личные_мысли", room="inbox", offset=0),
    )
    body = msg.answers[0][0]
    assert "(7 записей)" in body
    assert "первая" in body
    assert "вторая" in body
    data = [b.callback_data for row in
            (msg.answers[0][2].inline_keyboard) for b in row]
    assert "pn_v:0" in data
    assert "pn_v:1" in data
    assert "pn_p:5" in data
    assert not any(d.startswith("pn_p:0") for d in data)
    assert pn._list_state[4242]["offset"] == 0


def test_show_pn_page_back_and_forward(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(
        '{"drawers": [{"content": "a"}, {"content": "b"}, {"content": "c"}], '
        '"count": 12}',
    )
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    msg = FakeMessage()
    import asyncio

    asyncio.run(
        pn._show_pn_page(msg, msg.answer, wing="личные_мысли", room="inbox", offset=5),
    )
    data = [b.callback_data for row in
            (msg.answers[0][2].inline_keyboard) for b in row]
    assert "pn_p:0" in data
    assert "pn_p:10" in data
    assert "pn_b" in data


def test_show_pn_page_last_page_no_forward(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(
        '{"drawers": [{"content": "a"}], "count": 12}',
    )
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    msg = FakeMessage()
    import asyncio

    asyncio.run(
        pn._show_pn_page(msg, msg.answer, wing="личные_мысли", room="inbox", offset=10),
    )
    data = [b.callback_data for row in
            (msg.answers[0][2].inline_keyboard) for b in row]
    assert "pn_p:5" in data
    assert not any(d.startswith("pn_p:1") for d in data)


def test_show_pn_page_empty_drawer_content(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"drawers": [{"content": ""}], "count": 1}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    msg = FakeMessage()
    import asyncio

    asyncio.run(
        pn._show_pn_page(msg, msg.answer, wing="личные_мысли", room="inbox", offset=0),
    )
    assert "1." in msg.answers[0][0]


def test_show_pn_page_uid_from_int(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    edits = []
    import asyncio

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append(text)

    asyncio.run(
        pn._show_pn_page(4242, edit_func, wing="личные_мысли", room="inbox", offset=0),
    )
    assert edits == ["📖 Пока нет личных заметок."]


def test_show_pn_page_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(fail_on="mcp упал")
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    msg = FakeMessage()
    import asyncio

    asyncio.run(
        pn._show_pn_page(msg, msg.answer, wing="личные_мысли", room="inbox", offset=0),
    )
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in msg.answers[0][0]


# ---------- cb_pn_page / cb_pn_list_back ----------


def test_cb_pn_page_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data=None)
    import asyncio

    asyncio.run(pn.cb_pn_page(cb))
    assert cb.message.edits == []


def test_cb_pn_page_with_state(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    pn._list_state[4242] = {
        "wing": "крыло", "room": "комната", "offset": 0, "total": 0,
    }
    cb = FakeCb(data="pn_p:5")
    import asyncio

    asyncio.run(pn.cb_pn_page(cb))
    assert mcp.calls[0][1] == {
        "wing": "крыло", "room": "комната", "limit": 5, "offset": 5,
    }
    assert pn._list_state[4242]["offset"] == 5


def test_cb_pn_page_without_state(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_p:10")
    import asyncio

    asyncio.run(pn.cb_pn_page(cb))
    assert mcp.calls[0][1]["offset"] == 10
    assert mcp.calls[0][1]["wing"] == "личные_мысли"


def test_cb_pn_list_back(monkeypatch):
    _enable(monkeypatch)
    called = []

    async def fake_menu(m):
        called.append(m)

    monkeypatch.setattr(pn, "go_main_menu", fake_menu)
    pn._list_state[4242] = {"wing": "w"}
    pn._active_drawer[4242] = "d1"
    cb = FakeCb(data="pn_b")
    import asyncio

    asyncio.run(pn.cb_pn_list_back(cb))
    assert called == [cb.message]
    assert 4242 not in pn._list_state
    assert 4242 not in pn._active_drawer


def test_cb_pn_list_back_state_kept_on_menu_failure(monkeypatch):
    _enable(monkeypatch)

    async def fake_menu(m):
        raise RuntimeError("menu fail")

    monkeypatch.setattr(pn, "go_main_menu", fake_menu)
    pn._list_state[4242] = {"wing": "w"}
    pn._active_drawer[4242] = "d1"
    cb = FakeCb(data="pn_b")
    import asyncio

    with pytest.raises(RuntimeError, match="menu fail"):
        asyncio.run(pn.cb_pn_list_back(cb))
    assert pn._list_state[4242] == {"wing": "w"}
    assert pn._active_drawer[4242] == "d1"


def test_reopen_pn_list_show_page_error(monkeypatch):
    _enable(monkeypatch)

    async def boom(callback, edit_func, wing, room, offset):
        raise RuntimeError("list fail")

    monkeypatch.setattr(pn, "_show_pn_page", boom)
    cb = FakeCb(data="pn_v:0")
    import asyncio

    asyncio.run(pn._reopen_pn_list(cb))
    assert cb.message.edits[-1][0] == "❌ Не удалось открыть список."


# ---------- cb_pn_view ----------


def test_cb_pn_view_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data=None)
    import asyncio

    asyncio.run(pn.cb_pn_view(cb))
    assert cb.message.edits == []


def test_cb_pn_view_no_state(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_v:0")
    import asyncio

    asyncio.run(pn.cb_pn_view(cb))
    assert cb.message.edits[-1][0] == "📖 Пока нет личных заметок."


def test_cb_pn_view_idx_out_of_range(monkeypatch):
    _enable(monkeypatch)
    pn._list_state[4242] = {"drawers": [{"drawer_id": 1}]}
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_v:5")
    import asyncio

    asyncio.run(pn.cb_pn_view(cb))
    assert cb.message.edits[-1][0] == "📖 Пока нет личных заметок."


def test_cb_pn_view_success_short(monkeypatch):
    _enable(monkeypatch)
    pn._list_state[4242] = {"drawers": [{"drawer_id": "d1"}]}
    mcp = FakeMCP('{"content": "короткий текст", "wing": "крыло", "room": "r"}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_v:0")
    import asyncio

    asyncio.run(pn.cb_pn_view(cb))
    assert pn._active_drawer[4242] == "d1"
    body = cb.message.edits[-1][0]
    assert "короткий текст" in body
    assert "полный текст" not in body
    data = _markup_data(cb.message)
    assert "pn_r" in data
    assert "pn_tp" in data
    assert "pn_q" in data
    assert "pn_del" in data
    assert "pn_bl" in data


def test_cb_pn_view_success_long(monkeypatch):
    _enable(monkeypatch)
    pn._list_state[4242] = {"drawers": [{"drawer_id": "d1"}]}
    long_content = "с" * 400
    mcp = FakeMCP(f'{{"content": "{long_content}"}}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_v:0")
    import asyncio

    asyncio.run(pn.cb_pn_view(cb))
    body = cb.message.edits[-1][0]
    assert "…" in body
    assert "полный текст — после кнопки" in body


def test_cb_pn_view_error(monkeypatch):
    _enable(monkeypatch)
    pn._list_state[4242] = {"drawers": [{"drawer_id": "d1"}]}
    mcp = FakeMCP(fail_on="mcp упал")
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_v:0")
    import asyncio

    asyncio.run(pn.cb_pn_view(cb))
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in cb.message.edits[-1][0]


# ---------- cb_pn_read_full ----------


def test_cb_pn_read_full_no_drawer(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_r")
    import asyncio

    asyncio.run(pn.cb_pn_read_full(cb))
    assert cb.message.edits[-1][0] == "📖 Пока нет личных заметок."


def test_cb_pn_read_full_success(monkeypatch):
    _enable(monkeypatch)
    pn._active_drawer[4242] = "d1"
    mcp = FakeMCP('{"content": "полный текст заметки", "wing": "крыло", "room": "r"}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    monkeypatch.setattr(
        "services.text_formatter.split_message",
        lambda t, limit=4000: ["часть1", "часть2"],
    )
    cb = FakeCb(data="pn_r")
    import asyncio

    asyncio.run(pn.cb_pn_read_full(cb))
    assert cb.message.answers[0][0] == "часть1"
    body = cb.message.edits[-1][0]
    assert "часть2" in body
    assert _markup_data(cb.message)[0] == "pn_tp"


def test_cb_pn_read_full_error(monkeypatch):
    _enable(monkeypatch)
    pn._active_drawer[4242] = "d1"
    mcp = FakeMCP(fail_on="mcp упал")
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_r")
    import asyncio

    asyncio.run(pn.cb_pn_read_full(cb))
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in cb.message.edits[-1][0]


# ---------- cb_pn_back_to_list / cb_pn_back_to_view ----------


def test_cb_pn_back_to_list_with_state(monkeypatch):
    _enable(monkeypatch)
    pn._list_state[4242] = {
        "wing": "крыло", "room": "комната", "offset": 5, "total": 0,
    }
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_bl")
    import asyncio

    asyncio.run(pn.cb_pn_back_to_list(cb))
    assert mcp.calls[0][1] == {
        "wing": "крыло", "room": "комната", "limit": 5, "offset": 5,
    }


def test_cb_pn_back_to_list_without_state(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_bl")
    import asyncio

    asyncio.run(pn.cb_pn_back_to_list(cb))
    assert mcp.calls[0][1]["wing"] == "личные_мысли"


def test_cb_pn_back_to_view_with_state(monkeypatch):
    _enable(monkeypatch)
    pn._list_state[4242] = {
        "wing": "крыло", "room": "комната", "offset": 10, "total": 0,
    }
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_v")
    import asyncio

    asyncio.run(pn.cb_pn_back_to_view(cb))
    assert mcp.calls[0][1]["offset"] == 10


def test_cb_pn_back_to_view_without_state(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_v")
    import asyncio

    asyncio.run(pn.cb_pn_back_to_view(cb))
    assert mcp.calls[0][1]["offset"] == 0


# ---------- cb_pn_to_palace ----------


def test_cb_pn_to_palace_no_drawer(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_tp")
    import asyncio

    asyncio.run(pn.cb_pn_to_palace(cb))
    assert cb.message.edits[-1][0] == "📖 Пока нет личных заметок."


def test_cb_pn_to_palace_success(monkeypatch):
    _enable(monkeypatch)
    pn._active_drawer[4242] = "d1"
    mcp = FakeMCP('{"content": "текст для дворца"}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    shown = []

    async def fake_show_save_wings(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(
        "handlers.palace._show_save_wings", fake_show_save_wings,
    )
    cb = FakeCb(data="pn_tp")
    import asyncio

    asyncio.run(pn.cb_pn_to_palace(cb))
    from handlers.palace.save import _save_state

    assert _save_state[4242] == {
        "text": "текст для дворца",
        "mode": "full",
        "wing": "",
        "room": "",
        "wings": [],
        "rooms": [],
    }
    assert shown[0][1] == 4242


def test_cb_pn_to_palace_error(monkeypatch):
    _enable(monkeypatch)
    pn._active_drawer[4242] = "d1"
    mcp = FakeMCP(fail_on="mcp упал")
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_tp")
    import asyncio

    asyncio.run(pn.cb_pn_to_palace(cb))
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in cb.message.edits[-1][0]


# ---------- cb_pn_quote_prompt ----------


def test_cb_pn_quote_prompt_no_drawer(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_q")
    import asyncio

    asyncio.run(pn.cb_pn_quote_prompt(cb))
    assert cb.message.edits[-1][0] == "📖 Пока нет личных заметок."


def test_cb_pn_quote_prompt_success_short(monkeypatch):
    _enable(monkeypatch)
    pn._active_drawer[4242] = "d1"
    mcp = FakeMCP('{"content": "цитата"}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_q")
    import asyncio

    asyncio.run(pn.cb_pn_quote_prompt(cb))
    body = cb.message.edits[-1][0]
    assert "Отправьте цитату" in body
    assert "цитата" in body
    assert "…" not in body
    assert pn._quote_waiting[4242] == {"content": "цитата", "drawer_id": "d1"}


def test_cb_pn_quote_prompt_success_long(monkeypatch):
    _enable(monkeypatch)
    pn._active_drawer[4242] = "d1"
    long_content = "с" * 600
    mcp = FakeMCP(f'{{"content": "{long_content}"}}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_q")
    import asyncio

    asyncio.run(pn.cb_pn_quote_prompt(cb))
    assert "…" in cb.message.edits[-1][0]


def test_cb_pn_quote_prompt_error(monkeypatch):
    _enable(monkeypatch)
    pn._active_drawer[4242] = "d1"
    mcp = FakeMCP(fail_on="mcp упал")
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_q")
    import asyncio

    asyncio.run(pn.cb_pn_quote_prompt(cb))
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in cb.message.edits[-1][0]


# ---------- cb_pn_delete_confirm / cb_pn_delete_execute ----------


def test_cb_pn_delete_confirm_no_drawer(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_del")
    import asyncio

    asyncio.run(pn.cb_pn_delete_confirm(cb))
    assert cb.message.edits[-1][0] == "📖 Пока нет личных заметок."


def test_cb_pn_delete_confirm_success(monkeypatch):
    _enable(monkeypatch)
    pn._active_drawer[4242] = "d1"
    cb = FakeCb(data="pn_del")
    import asyncio

    asyncio.run(pn.cb_pn_delete_confirm(cb))
    body = cb.message.edits[-1][0]
    assert "Удалить заметку?" in body
    data = _markup_data(cb.message)
    assert "pn_del_yes" in data
    assert "pn_v" in data


def test_cb_pn_delete_execute_no_drawer(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"drawers": [], "count": 0}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_del_yes")
    import asyncio

    asyncio.run(pn.cb_pn_delete_execute(cb))
    assert cb.message.edits[-1][0] == "📖 Пока нет личных заметок."


def test_cb_pn_delete_execute_success(monkeypatch):
    _enable(monkeypatch)
    pn._active_drawer[4242] = "d1"
    pn._list_state[4242] = {"wing": "w"}
    mcp = FakeMCP('{"success": true}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_del_yes")
    import asyncio

    asyncio.run(pn.cb_pn_delete_execute(cb))
    assert cb.message.edits[-1] == ("✅ Заметка удалена.", None, None)
    assert mcp.calls[0] == ("mempalace_delete_drawer", {"drawer_id": "d1"})
    assert 4242 not in pn._list_state
    assert 4242 not in pn._active_drawer


def test_cb_pn_delete_execute_failure(monkeypatch):
    _enable(monkeypatch)
    pn._active_drawer[4242] = "d1"
    mcp = FakeMCP('{"success": false}')
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_del_yes")
    import asyncio

    asyncio.run(pn.cb_pn_delete_execute(cb))
    assert "❌ Ошибка:" in cb.message.edits[-1][0]


def test_cb_pn_delete_execute_empty_response(monkeypatch):
    _enable(monkeypatch)
    pn._active_drawer[4242] = "d1"
    mcp = FakeMCP("")
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_del_yes")
    import asyncio

    asyncio.run(pn.cb_pn_delete_execute(cb))
    assert "❌ Ошибка:" in cb.message.edits[-1][0]


def test_cb_pn_delete_execute_error(monkeypatch):
    _enable(monkeypatch)
    pn._active_drawer[4242] = "d1"
    mcp = FakeMCP(fail_on="mcp упал")
    monkeypatch.setattr(pn, "get_mcp", lambda: mcp)
    cb = FakeCb(data="pn_del_yes")
    import asyncio

    asyncio.run(pn.cb_pn_delete_execute(cb))
    # format_user_error для RuntimeError возвращает "❌ Ошибка выполнения"
    assert "Ошибка выполнения" in cb.message.edits[-1][0]


# ---------- _save_quote_to_palace ----------


def test_save_quote_to_palace_no_data():
    import asyncio

    answered = []

    async def answer_func(text):
        answered.append(text)
        return None

    asyncio.run(pn._save_quote_to_palace(4242, "цитата", answer_func))
    assert answered == []


def test_save_quote_to_palace_success(monkeypatch):
    _enable(monkeypatch)
    pn._quote_waiting[4242] = {"content": "цитата", "drawer_id": "d1"}
    shown = []

    async def fake_show_save_wings(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(
        "handlers.palace._show_save_wings", fake_show_save_wings,
    )
    msg = FakeMessage()
    import asyncio

    asyncio.run(pn._save_quote_to_palace(4242, " цитата ", msg.answer))
    from handlers.palace.save import _save_state

    assert _save_state[4242]["text"] == "цитата"
    assert shown[0][1] == 4242
    assert 4242 not in pn._quote_waiting
    assert msg.answers[0] == (
        "💬 Цитата получена. Выберите куда сохранить...", None, None,
    )


# ---------- not allowed callbacks ----------


@pytest.mark.parametrize(
    "data",
    ["pn_cf", "pn_reclass", "pn_wing:0", "pn_room:0", "pn_cancel", "pn_p:0",
     "pn_b", "pn_v:0", "pn_r", "pn_bl", "pn_v", "pn_tp", "pn_q", "pn_del",
     "pn_del_yes"],
)
def test_callbacks_not_allowed(monkeypatch, data):
    _enable(monkeypatch)
    cb = FakeCb(uid=999, data=data)
    import asyncio

    asyncio.run(_dispatch(cb))
    assert cb.answered == [("❌ Нет доступа", True)]


async def _dispatch(cb):
    mapping = {
        "pn_cf": pn.cb_pn_save,
        "pn_reclass": pn.cb_pn_reclass,
        "pn_cancel": pn.cb_pn_cancel,
        "pn_p:0": pn.cb_pn_page,
        "pn_b": pn.cb_pn_list_back,
        "pn_r": pn.cb_pn_read_full,
        "pn_bl": pn.cb_pn_back_to_list,
        "pn_v": pn.cb_pn_back_to_view,
        "pn_tp": pn.cb_pn_to_palace,
        "pn_q": pn.cb_pn_quote_prompt,
        "pn_del": pn.cb_pn_delete_confirm,
        "pn_del_yes": pn.cb_pn_delete_execute,
    }
    if data := cb.data:
        if data.startswith("pn_wing:"):
            await pn.cb_pn_wing(cb)
        elif data.startswith("pn_room:"):
            await pn.cb_pn_room(cb)
        elif data.startswith("pn_v:"):
            await pn.cb_pn_view(cb)
        else:
            await mapping[data](cb)
