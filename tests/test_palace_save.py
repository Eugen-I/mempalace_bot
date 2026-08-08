"""Unit tests for handlers.palace.save."""

from types import SimpleNamespace

import pytest

from handlers.palace import save as s


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeMessage:
    def __init__(self, uid=4242, text="", html_text=None, reply_to_message=None,
                 caption=""):
        self.from_user = FakeUser(uid)
        self.text = text
        self.html_text = html_text
        self.reply_to_message = reply_to_message
        self.caption = caption
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


def _enable(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    monkeypatch.setattr(s, "safe_html_format", lambda t: t)


@pytest.fixture(autouse=True)
def _clean_state():
    s._save_state.pop(4242, None)
    s._pending_mcp_input.pop(4242, None)
    s._wing_cache.pop(4242, None)
    s._room_cache.pop(4242, None)
    yield
    s._save_state.pop(4242, None)
    s._pending_mcp_input.pop(4242, None)
    s._wing_cache.pop(4242, None)
    s._room_cache.pop(4242, None)


def _kb_data(markup):
    if markup is None:
        return []
    return [b.callback_data for row in markup.inline_keyboard for b in row]


def _kb_texts(markup):
    if markup is None:
        return []
    return [b.text for row in markup.inline_keyboard for b in row]


# ---------- cb_save_start ----------


def test_cb_save_start_from_html_text(monkeypatch):
    _enable(monkeypatch)
    shown = []

    async def fake_show_wings(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_show_save_wings", fake_show_wings)
    msg = FakeMessage(html_text="<b>оригинал</b>")
    cb = FakeCb(data="p_sv", message=msg)
    import asyncio

    asyncio.run(s.cb_save_start(cb))
    assert s._save_state[4242] == {"text": "<b>оригинал</b>", "mode": "full"}
    assert shown[0][1] == 4242
    assert shown[0][0].__self__ is cb.message


def test_cb_save_start_from_reply(monkeypatch):
    _enable(monkeypatch)
    shown = []

    async def fake_show_wings(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_show_save_wings", fake_show_wings)
    rtm = FakeMessage(html_text="ответ текст", caption="")
    msg = FakeMessage(uid=4242, text="", html_text=None, reply_to_message=rtm)
    cb = FakeCb(data="p_sv", message=msg)
    import asyncio

    asyncio.run(s.cb_save_start(cb))
    assert s._save_state[4242]["text"] == "ответ текст"


def test_cb_save_start_from_ai_cache(monkeypatch):
    _enable(monkeypatch)
    shown = []

    async def fake_show_wings(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_show_save_wings", fake_show_wings)
    from services.ai_cache import _ai_msg_cache

    monkeypatch.setattr(s, "_ai_msg_cache", {100: {5: "кэшированный ответ"}})
    msg = FakeMessage(html_text="", text="", reply_to_message=None)
    cb = FakeCb(data="p_sv", message=msg)
    import asyncio

    asyncio.run(s.cb_save_start(cb))
    assert s._save_state[4242]["text"] == "кэшированный ответ"


def test_cb_save_start_from_ai_cache_empty(monkeypatch):
    _enable(monkeypatch)
    shown = []

    async def fake_show_wings(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_show_save_wings", fake_show_wings)
    from services.ai_cache import _ai_msg_cache

    monkeypatch.setattr(s, "_ai_msg_cache", {100: {}, 200: {3: "хвост"}})
    msg = FakeMessage(html_text="", text="", reply_to_message=None)
    cb = FakeCb(data="p_sv", message=msg)
    import asyncio

    asyncio.run(s.cb_save_start(cb))
    assert s._save_state[4242]["text"] == "хвост"


def test_cb_save_start_ai_cache_all_empty(monkeypatch):
    _enable(monkeypatch)
    shown = []

    async def fake_show_wings(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_show_save_wings", fake_show_wings)
    from services.ai_cache import _ai_msg_cache

    monkeypatch.setattr(s, "_ai_msg_cache", {100: {}, 200: {}})
    msg = FakeMessage(html_text="", text="", reply_to_message=None)
    cb = FakeCb(data="p_sv", message=msg)
    import asyncio

    asyncio.run(s.cb_save_start(cb))
    assert msg.answers[0][0] == "❌ Нет текста для сохранения."
    assert shown == []


def test_cb_save_start_no_text(monkeypatch):
    _enable(monkeypatch)
    shown = []

    async def fake_show_wings(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_show_save_wings", fake_show_wings)
    from services.ai_cache import _ai_msg_cache

    monkeypatch.setattr(s, "_ai_msg_cache", {})
    msg = FakeMessage(html_text="", text="", reply_to_message=None)
    cb = FakeCb(data="p_sv", message=msg)
    import asyncio

    asyncio.run(s.cb_save_start(cb))
    assert msg.answers[0][0] == "❌ Нет текста для сохранения."
    assert shown == []


# ---------- cb_save_cancel ----------


def test_cb_save_cancel(monkeypatch):
    _enable(monkeypatch)
    s._save_state[4242] = {"text": "x"}
    cb = FakeCb(data="p_sv_x")
    import asyncio

    asyncio.run(s.cb_save_cancel(cb))
    assert msg_answers(cb) == "❌ Сохранение отменено."
    assert 4242 not in s._save_state


def msg_answers(cb):
    return cb.message.answers[0][0]


# ---------- cb_save_all ----------


def test_cb_save_all_with_state(monkeypatch):
    _enable(monkeypatch)
    s._save_state[4242] = {"text": "x", "mode": "quote"}
    shown = []

    async def fake_show_wings(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_show_save_wings", fake_show_wings)
    cb = FakeCb(data="p_sv_a")
    import asyncio

    asyncio.run(s.cb_save_all(cb))
    assert s._save_state[4242]["mode"] == "full"
    assert shown[0][1] == 4242


def test_cb_save_all_without_state(monkeypatch):
    _enable(monkeypatch)
    shown = []

    async def fake_show_wings(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_show_save_wings", fake_show_wings)
    cb = FakeCb(data="p_sv_a")
    import asyncio

    asyncio.run(s.cb_save_all(cb))
    assert shown[0][1] == 4242


# ---------- cb_save_quote_prompt ----------


def test_cb_save_quote_prompt(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_sv_q")
    import asyncio

    asyncio.run(s.cb_save_quote_prompt(cb))
    assert s._pending_mcp_input[4242] == "save_quote"
    assert "Введите цитату" in cb.message.edits[-1][0]


# ---------- _show_save_wings ----------


def test_show_save_wings_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"wings": {"крыло1": {}, "крыло2": {}}}')
    monkeypatch.setattr(s, "get_mcp", lambda: mcp)
    edits = []
    import asyncio

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append((text, parse_mode, reply_markup))

    asyncio.run(s._show_save_wings(edit_func, 4242))
    assert edits[0][1] == "Markdown"
    assert _kb_data(edits[0][2]) == ["p_sw_0", "p_sw_1", "p_sv_nw", "p_sv_x"]
    assert s._wing_cache[4242] == ["крыло1", "крыло2"]


def test_show_save_wings_parsed_list(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP('{"wings": ["a", "b"]}')
    monkeypatch.setattr(s, "get_mcp", lambda: mcp)
    edits = []
    import asyncio

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append(text)

    asyncio.run(s._show_save_wings(edit_func, 4242))
    assert s._wing_cache[4242] == ["a", "b"]


def test_show_save_wings_error_empty(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP(fail_on="mcp упал")
    monkeypatch.setattr(s, "get_mcp", lambda: mcp)
    edits = []
    import asyncio

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append(text)

    asyncio.run(s._show_save_wings(edit_func, 4242))
    assert edits == ["❌ Не удалось загрузить крылья."]


# ---------- cb_save_wing_chosen ----------


def test_cb_save_wing_chosen_success(monkeypatch):
    _enable(monkeypatch)
    s._wing_cache[4242] = ["крыло1", "крыло2"]
    s._save_state[4242] = {"text": "x"}
    shown = []

    async def fake_show_rooms(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_show_save_rooms", fake_show_rooms)
    cb = FakeCb(data="p_sw_1")
    import asyncio

    asyncio.run(s.cb_save_wing_chosen(cb))
    assert s._save_state[4242]["wing"] == "крыло2"
    assert shown[0][1] == 4242


def test_cb_save_wing_chosen_bad_index(monkeypatch):
    _enable(monkeypatch)
    s._wing_cache[4242] = ["крыло1"]
    cb = FakeCb(data="p_sw_abc")
    import asyncio

    asyncio.run(s.cb_save_wing_chosen(cb))
    assert cb.message.edits == []


def test_cb_save_wing_chosen_no_cache(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_sw_0")
    import asyncio

    asyncio.run(s.cb_save_wing_chosen(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла."


def test_cb_save_wing_chosen_out_of_range(monkeypatch):
    _enable(monkeypatch)
    s._wing_cache[4242] = ["крыло1"]
    cb = FakeCb(data="p_sw_5")
    import asyncio

    asyncio.run(s.cb_save_wing_chosen(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла."


def test_cb_save_wing_chosen_no_state(monkeypatch):
    _enable(monkeypatch)
    s._wing_cache[4242] = ["крыло1"]
    shown = []

    async def fake_show_rooms(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_show_save_rooms", fake_show_rooms)
    cb = FakeCb(data="p_sw_0")
    import asyncio

    asyncio.run(s.cb_save_wing_chosen(cb))
    assert shown[0][1] == 4242


# ---------- cb_save_new_wing_prompt ----------


def test_cb_save_new_wing_prompt(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_sv_nw")
    import asyncio

    asyncio.run(s.cb_save_new_wing_prompt(cb))
    assert s._pending_mcp_input[4242] == "save_new_wing"
    assert "Введите название нового крыла" in cb.message.edits[-1][0]


# ---------- _show_save_rooms ----------


def test_show_save_rooms_success(monkeypatch):
    _enable(monkeypatch)
    s._save_state[4242] = {"text": "x", "wing": "крыло"}
    mcp = FakeMCP('{"rooms": {"комната1": {}, "комната2": {}}}')
    monkeypatch.setattr(s, "get_mcp", lambda: mcp)
    edits = []
    import asyncio

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append((text, parse_mode, reply_markup))

    asyncio.run(s._show_save_rooms(edit_func, 4242))
    body = edits[0][0]
    assert "Крыло: <b>крыло</b>" in body
    assert edits[0][1] == "HTML"
    assert _kb_data(edits[0][2]) == [
        "p_sr_0", "p_sr_1", "p_sv_nr", "p_sv_bw", "p_sv_x",
    ]
    assert s._room_cache[4242] == [("комната1", {}), ("комната2", {})]


def test_show_save_rooms_no_state(monkeypatch):
    _enable(monkeypatch)
    edits = []
    import asyncio

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append(text)

    asyncio.run(s._show_save_rooms(edit_func, 4242))
    assert edits == ["❌ Сессия истекла."]


def test_show_save_rooms_no_rooms(monkeypatch):
    _enable(monkeypatch)
    s._save_state[4242] = {"text": "x", "wing": "крыло"}
    mcp = FakeMCP('{"rooms": {}}')
    monkeypatch.setattr(s, "get_mcp", lambda: mcp)
    edits = []
    import asyncio

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append((text, parse_mode, reply_markup))

    asyncio.run(s._show_save_rooms(edit_func, 4242))
    assert "нет комнат. Создать?" in edits[0][0]
    assert _kb_data(edits[0][2]) == ["p_sv_nr", "p_sv_x"]


def test_show_save_rooms_error(monkeypatch):
    _enable(monkeypatch)
    s._save_state[4242] = {"text": "x", "wing": "крыло"}
    mcp = FakeMCP(fail_on="mcp упал")
    monkeypatch.setattr(s, "get_mcp", lambda: mcp)
    edits = []
    import asyncio

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append((text, parse_mode, reply_markup))

    asyncio.run(s._show_save_rooms(edit_func, 4242))
    assert "нет комнат. Создать?" in edits[0][0]


# ---------- cb_save_back_to_wings ----------


def test_cb_save_back_to_wings(monkeypatch):
    _enable(monkeypatch)
    shown = []

    async def fake_show_wings(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_show_save_wings", fake_show_wings)
    cb = FakeCb(data="p_sv_bw")
    import asyncio

    asyncio.run(s.cb_save_back_to_wings(cb))
    assert shown[0][1] == 4242


# ---------- cb_save_room_chosen ----------


def test_cb_save_room_chosen_success(monkeypatch):
    _enable(monkeypatch)
    s._room_cache[4242] = [("комната1", {}), ("комната2", {})]
    s._save_state[4242] = {"text": "x", "wing": "крыло"}
    shown = []

    async def fake_confirm(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_save_confirm", fake_confirm)
    cb = FakeCb(data="p_sr_1")
    import asyncio

    asyncio.run(s.cb_save_room_chosen(cb))
    assert s._save_state[4242]["room"] == "комната2"
    assert shown[0][1] == 4242


def test_cb_save_room_chosen_bad_index(monkeypatch):
    _enable(monkeypatch)
    s._room_cache[4242] = [("комната1", {})]
    cb = FakeCb(data="p_sr_abc")
    import asyncio

    asyncio.run(s.cb_save_room_chosen(cb))
    assert cb.message.edits == []


def test_cb_save_room_chosen_no_state(monkeypatch):
    _enable(monkeypatch)
    s._room_cache[4242] = [("комната1", {})]
    shown = []

    async def fake_confirm(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_save_confirm", fake_confirm)
    cb = FakeCb(data="p_sr_0")
    import asyncio

    asyncio.run(s.cb_save_room_chosen(cb))
    assert shown[0][1] == 4242


def test_cb_save_room_chosen_no_cache(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_sr_0")
    import asyncio

    asyncio.run(s.cb_save_room_chosen(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла."


def test_cb_save_room_chosen_out_of_range(monkeypatch):
    _enable(monkeypatch)
    s._room_cache[4242] = [("комната1", {})]
    cb = FakeCb(data="p_sr_5")
    import asyncio

    asyncio.run(s.cb_save_room_chosen(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла."


# ---------- cb_save_new_room_prompt ----------


def test_cb_save_new_room_prompt(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_sv_nr")
    import asyncio

    asyncio.run(s.cb_save_new_room_prompt(cb))
    assert s._pending_mcp_input[4242] == "save_new_room"
    assert "Введите название новой комнаты" in cb.message.edits[-1][0]


# ---------- _save_confirm ----------


def test_save_confirm_full(monkeypatch):
    _enable(monkeypatch)
    s._save_state[4242] = {
        "text": "длинный текст", "wing": "крыло", "room": "комната",
        "mode": "full",
    }
    edits = []
    import asyncio

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append((text, parse_mode, reply_markup))

    asyncio.run(s._save_confirm(edit_func, 4242))
    body = edits[0][0]
    assert "Подтверждение сохранения" in body
    assert "Режим: Полный текст" in body
    assert _kb_data(edits[0][2]) == ["p_sv_c", "p_sv_br", "p_sv_bw", "p_sv_x"]


def test_save_confirm_quote(monkeypatch):
    _enable(monkeypatch)
    s._save_state[4242] = {
        "text": "цитата", "wing": "крыло", "room": "комната", "mode": "quote",
    }
    edits = []
    import asyncio

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append(text)

    asyncio.run(s._save_confirm(edit_func, 4242))
    assert "Режим: Цитата" in edits[0]


def test_save_confirm_no_state(monkeypatch):
    _enable(monkeypatch)
    edits = []
    import asyncio

    async def edit_func(text, parse_mode=None, reply_markup=None):
        edits.append(text)

    asyncio.run(s._save_confirm(edit_func, 4242))
    assert edits == ["❌ Сессия истекла."]


# ---------- cb_save_back_to_rooms ----------


def test_cb_save_back_to_rooms(monkeypatch):
    _enable(monkeypatch)
    shown = []

    async def fake_show_rooms(edit_func, uid):
        shown.append((edit_func, uid))

    monkeypatch.setattr(s, "_show_save_rooms", fake_show_rooms)
    cb = FakeCb(data="p_sv_br")
    import asyncio

    asyncio.run(s.cb_save_back_to_rooms(cb))
    assert shown[0][1] == 4242


# ---------- cb_save_confirm_execute ----------


def test_cb_save_confirm_execute_no_state(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_sv_c")
    import asyncio

    asyncio.run(s.cb_save_confirm_execute(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла."


def test_cb_save_confirm_execute_full(monkeypatch):
    _enable(monkeypatch)
    s._save_state[4242] = {
        "text": "текст", "wing": "крыло", "room": "комната", "mode": "full",
    }
    mcp = FakeMCP('{"drawer_id": "d1"}')
    monkeypatch.setattr(s, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_sv_c")
    import asyncio

    asyncio.run(s.cb_save_confirm_execute(cb))
    assert mcp.calls[0][0] == "mempalace_add_drawer"
    assert mcp.calls[0][1]["content"] == "текст"
    body = cb.message.edits[-1][0]
    assert "Сохранено в" in body
    assert "d1" in body


def test_cb_save_confirm_execute_quote(monkeypatch):
    _enable(monkeypatch)
    s._save_state[4242] = {
        "text": "цитата", "wing": "крыло", "room": "комната", "mode": "quote",
    }
    mcp = FakeMCP('{"drawer_id": "d2"}')
    monkeypatch.setattr(s, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_sv_c")
    import asyncio

    asyncio.run(s.cb_save_confirm_execute(cb))
    assert mcp.calls[0][1]["content"] == "> цитата\n\n— из диалога с ИИ"


def test_cb_save_confirm_execute_error(monkeypatch):
    _enable(monkeypatch)
    s._save_state[4242] = {"text": "x", "mode": "full"}
    mcp = FakeMCP(fail_on="mcp упал")
    monkeypatch.setattr(s, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_sv_c")
    import asyncio

    asyncio.run(s.cb_save_confirm_execute(cb))
    assert "❌ Ошибка сохранения: mcp упал" in cb.message.edits[-1][0]


# ---------- _format_save_result ----------


def test_format_save_result_plain(monkeypatch):
    _enable(monkeypatch)
    out = s._format_save_result("не json", "w", "r")
    assert "Сохранено в" in out
    assert "w/r" in out


def test_format_save_result_empty(monkeypatch):
    _enable(monkeypatch)
    out = s._format_save_result("", "w", "r")
    assert "Сохранено в" in out


def test_format_save_result_success(monkeypatch):
    _enable(monkeypatch)
    out = s._format_save_result('{"drawer_id": "abc"}', "w", "r")
    assert "abc" in out


def test_format_save_result_failed(monkeypatch):
    _enable(monkeypatch)
    out = s._format_save_result('{"success": false, "error": "дубликат"}', "w", "r")
    assert "❌ Ошибка сохранения" in out
    assert "дубликат" in out


def test_format_save_result_failed_no_error(monkeypatch):
    _enable(monkeypatch)
    out = s._format_save_result('{"success": false}', "w", "r")
    assert "не удалось сохранить" in out


def test_format_save_result_other_json(monkeypatch):
    _enable(monkeypatch)
    out = s._format_save_result('[1, 2]', "w", "r")
    assert "Сохранено в" in out


# ---------- not allowed ----------


@pytest.mark.parametrize("data", ["p_sv", "p_sv_x", "p_sv_a", "p_sv_q",
                                  "p_sw_0", "p_sv_nw", "p_sv_bw", "p_sr_0",
                                  "p_sv_nr", "p_sv_br", "p_sv_c"])
def test_callbacks_not_allowed(monkeypatch, data):
    _enable(monkeypatch)
    cb = FakeCb(uid=999, data=data)
    import asyncio

    asyncio.run(_dispatch(cb))
    assert cb.answered == [("❌ Нет доступа", True)]


async def _dispatch(cb):
    if not cb.data:
        return
    if cb.data.startswith("p_sw_"):
        await s.cb_save_wing_chosen(cb)
    elif cb.data.startswith("p_sr_"):
        await s.cb_save_room_chosen(cb)
    else:
        mapping = {
            "p_sv": s.cb_save_start,
            "p_sv_x": s.cb_save_cancel,
            "p_sv_a": s.cb_save_all,
            "p_sv_q": s.cb_save_quote_prompt,
            "p_sv_nw": s.cb_save_new_wing_prompt,
            "p_sv_bw": s.cb_save_back_to_wings,
            "p_sv_nr": s.cb_save_new_room_prompt,
            "p_sv_br": s.cb_save_back_to_rooms,
            "p_sv_c": s.cb_save_confirm_execute,
        }
        await mapping[cb.data](cb)
