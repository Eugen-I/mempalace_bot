"""Unit tests for handlers.search."""

import json
from types import SimpleNamespace

import pytest

from handlers import search as sh


class FakeUser:
    def __init__(self, uid):
        self.id = uid


class FakeChat:
    def __init__(self, cid):
        self.id = cid


class FakeMessage:
    def __init__(self, uid=4242, text=""):
        self.from_user = FakeUser(uid)
        self.chat = FakeChat(1)
        self.text = text
        self.answers = []
        self.status = None

    async def answer(self, text, parse_mode=None, reply_markup=None):
        self.answers.append((text, parse_mode, reply_markup))
        self.status = FakeStatus()
        return self.status

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.edits = getattr(self, "edits", [])
        self.edits.append((text, parse_mode))
        return self.status


class FakeStatus:
    def __init__(self):
        self.edited = []
        self.deleted = False

    async def edit_text(self, text, parse_mode=None):
        self.edited.append(text)

    async def delete(self):
        self.deleted = True


class FakeCb:
    def __init__(self, uid=4242, data=""):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = FakeMessage(uid)
        self.answered = []
        self.message_edits = []

    async def answer(self, text=None, show_alert=None):
        self.answered.append((text, show_alert))

    async def edit_text(self, text, parse_mode=None, reply_markup=None):
        self.message_edits.append((text, parse_mode, reply_markup))


def _enable(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {4242})
    monkeypatch.setattr(sh, "_pending_wing_search", {})
    monkeypatch.setattr(sh, "search_result_cache", {})
    monkeypatch.setattr(sh, "source_drawer_cache", {})
    return sh._pending_wing_search


class FakeMCP:
    def __init__(self, responses):
        self.responses = responses  # dict[str, str] by tool name
        self.calls = []

    async def call_tool(self, name, params):
        self.calls.append((name, params))
        if name in self.responses:
            return self.responses[name]
        raise RuntimeError(f"unexpected {name}")


# ---------- _open_room_view ----------


@pytest.mark.asyncio
async def test_open_room_view_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP({
        "mempalace_list_drawers":
            json.dumps({
                "drawers": [
                    {"drawer_id": "d1", "closet_name": "Шкаф", "content_preview": "текст превью"},
                    {"drawer_id": "d2", "content": "второй"},
                ],
                "count": 7,
            }),
    })
    monkeypatch.setattr(sh, "get_mcp", lambda: mcp)
    edits = []
    await sh._open_room_view(_edits(edits), 4242, "w", "r")
    assert len(edits) == 1
    assert "Записи в w/r" in edits[0][0]
    assert edits[0][2] is not None  # reply_markup
    assert mcp.calls[0][0] == "mempalace_list_drawers"


@pytest.mark.asyncio
async def test_open_room_view_empty(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP({
        "mempalace_list_drawers":
            json.dumps({"drawers": [], "count": 0}),
    })
    monkeypatch.setattr(sh, "get_mcp", lambda: mcp)
    edits = []
    await sh._open_room_view(_edits(edits), 4242, "w", "r")
    assert "нет записей" in edits[0][0]
    assert edits[0][2] is None


@pytest.mark.asyncio
async def test_open_room_view_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP({})

    async def boom(name, params):
        raise RuntimeError("mcp down")

    mcp.call_tool = boom
    monkeypatch.setattr(sh, "get_mcp", lambda: mcp)
    edits = []
    await sh._open_room_view(_edits(edits), 4242, "w", "r")
    assert "Ошибка" in edits[0][0]


def _edits(store):
    async def _inner(text, parse_mode=None, reply_markup=None):
        store.append((text, parse_mode, reply_markup))

    return _inner


# ---------- cmd_wing_search_prompt / cb ----------


@pytest.mark.asyncio
async def test_cmd_wing_search_prompt(monkeypatch):
    _enable(monkeypatch)
    msg = FakeMessage(4242)
    await sh.cmd_wing_search_prompt(msg)
    assert msg.answers[0][0] == "🔍 Выберите крыло для поиска:"
    assert msg.answers[0][2] is not None


@pytest.mark.asyncio
async def test_cb_search_wing(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="search:wing")
    await sh.cb_search_wing(cb)
    assert cb.message.answers[0][0] == "🔍 Выберите крыло для поиска:"
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_wing_search_select_known(monkeypatch):
    pending = _enable(monkeypatch)
    cb = FakeCb(4242, data="wing_search:dreams")
    await sh.cb_wing_search_select(cb)
    assert pending[4242] == "dreams"
    assert "Сны" in cb.message.edits[0][0]
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_wing_search_select_unknown(monkeypatch):
    pending = _enable(monkeypatch)
    cb = FakeCb(4242, data="wing_search:other")
    await sh.cb_wing_search_select(cb)
    assert pending[4242] == "other"
    assert "other" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_wing_search_select_not_allowed(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(999, data="wing_search:dreams")
    await sh.cb_wing_search_select(cb)
    assert getattr(cb.message, "edits", []) == []


# ---------- cmd_search ----------


@pytest.mark.asyncio
async def test_cmd_search_no_query(monkeypatch):
    _enable(monkeypatch)
    msg = FakeMessage(4242, text="/search")
    await sh.cmd_search(msg)
    assert "Укажите запрос" in msg.answers[0][0]


@pytest.mark.asyncio
async def test_cmd_search_basic(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(
        sh, "search_palace_with_sources",
        _async_result(("результат", [{"id": 1, "wing": "dreams", "room": "r", "file": "f"}])),
    )
    monkeypatch.setattr(sh, "send_text_only", _async_none)
    monkeypatch.setattr(sh, "split_message", lambda t: [t])
    msg = FakeMessage(4242, text="/search сон")
    await sh.cmd_search(msg)
    assert "результат" in msg.answers[1][0]
    assert sh.search_result_cache[4242] == [{"id": 1, "wing": "dreams", "room": "r", "file": "f"}]


@pytest.mark.asyncio
async def test_cmd_search_with_wing(monkeypatch):
    _enable(monkeypatch)
    captured = {}

    async def fake_search(text, limit=5, wing=""):
        captured["text"] = text
        captured["wing"] = wing
        return "найдено", []

    monkeypatch.setattr(sh, "search_palace_with_sources", fake_search)
    monkeypatch.setattr(sh, "send_text_only", _async_none)
    monkeypatch.setattr(sh, "split_message", lambda t: [t])
    msg = FakeMessage(4242, text="/search --wing dreams сон")
    await sh.cmd_search(msg)
    assert captured["text"] == "сон"
    assert captured["wing"] == "dreams"


@pytest.mark.asyncio
async def test_cmd_search_invalid_wing_ignored(monkeypatch):
    _enable(monkeypatch)
    captured = {}

    async def fake_search(text, limit=5, wing=""):
        captured["text"] = text
        captured["wing"] = wing
        return "найдено", []

    monkeypatch.setattr(sh, "search_palace_with_sources", fake_search)
    monkeypatch.setattr(sh, "send_text_only", _async_none)
    monkeypatch.setattr(sh, "split_message", lambda t: [t])
    msg = FakeMessage(4242, text="/search --wing bad сон")
    await sh.cmd_search(msg)
    assert captured["text"] == "сон"
    assert captured["wing"] == ""


@pytest.mark.asyncio
async def test_cmd_search_empty_result(monkeypatch):
    _enable(monkeypatch)
    sent = []
    monkeypatch.setattr(sh, "search_palace_with_sources", _async_result(("", [])))
    monkeypatch.setattr(sh, "send_text_only", _async_append(sent))
    msg = FakeMessage(4242, text="/search ничего")
    await sh.cmd_search(msg)
    assert sent == ["Ничего не найдено."]


@pytest.mark.asyncio
async def test_cmd_search_error(monkeypatch):
    _enable(monkeypatch)

    async def boom(text, limit=5, wing=""):
        raise RuntimeError("search down")

    monkeypatch.setattr(sh, "search_palace_with_sources", boom)
    msg = FakeMessage(4242, text="/search сон")
    await sh.cmd_search(msg)
    assert msg.status.edited == ["❌ Ошибка поиска: search down"]


@pytest.mark.asyncio
async def test_cmd_search_multiple_parts(monkeypatch):
    _enable(monkeypatch)
    sent = []
    monkeypatch.setattr(sh, "search_palace_with_sources", _async_result(("длинный", [])))
    monkeypatch.setattr(sh, "send_text_only", _async_append(sent))
    monkeypatch.setattr(sh, "split_message", lambda t: ["часть1", "часть2"])
    msg = FakeMessage(4242, text="/search сон")
    await sh.cmd_search(msg)
    assert sent == ["часть2"]


@pytest.mark.asyncio
async def test_cmd_search_not_allowed(monkeypatch):
    _enable(monkeypatch)
    msg = FakeMessage(999, text="/search сон")
    await sh.cmd_search(msg)
    assert msg.answers == []


def _async_result(value):
    async def _inner(*a, **kw):
        return value

    return _inner


async def _async_none(*a, **kw):
    return None


def _async_append(store):
    async def _inner(msg, text):
        store.append(text)

    return _inner


# ---------- cb_search_source_open ----------


@pytest.mark.asyncio
async def test_cb_search_source_open_success(monkeypatch):
    _enable(monkeypatch)
    sh.search_result_cache[4242] = [{"id": 5, "wing": "dreams", "room": "r", "file": "f"}]
    mcp = FakeMCP({
        "mempalace_list_drawers":
            json.dumps({"drawers": [{"drawer_id": "d1", "content": "контент"}], "count": 1}),
    })
    monkeypatch.setattr(sh, "get_mcp", lambda: mcp)
    cb = FakeCb(4242, data="p_src:5")
    await sh.cb_search_source_open(cb)
    assert cb.answered == [(None, None)]
    assert any("Записи" in e[0] for e in cb.message.edits)


@pytest.mark.asyncio
async def test_cb_search_source_open_not_in_cache(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="p_src:99")
    await sh.cb_search_source_open(cb)
    assert cb.message.edits[0][0] == "❌ Результаты поиска устарели."


@pytest.mark.asyncio
async def test_cb_search_source_open_no_wing_room(monkeypatch):
    _enable(monkeypatch)
    sh.search_result_cache[4242] = [{"id": 1, "wing": "", "room": "", "file": "f"}]
    cb = FakeCb(4242, data="p_src:1")
    await sh.cb_search_source_open(cb)
    assert "не содержит wing/room" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_search_source_open_bad_id(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="p_src:abc")
    await sh.cb_search_source_open(cb)
    assert getattr(cb.message, "edits", []) == []
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_search_source_open_short_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="p_src")
    await sh.cb_search_source_open(cb)
    assert cb.answered == [(None, None)]


# ---------- cb_search_source_drawer ----------


@pytest.mark.asyncio
async def test_cb_search_source_drawer_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP({
        "mempalace_get_drawer":
            json.dumps({"content": "контент ящика"}),
    })
    monkeypatch.setattr(sh, "get_mcp", lambda: mcp)
    cb = FakeCb(4242, data="p_srcdr:dreams:r:d1")
    await sh.cb_search_source_drawer(cb)
    assert any("контент ящика" in e[0] for e in cb.message.edits)
    assert 4242 in sh.source_drawer_cache


@pytest.mark.asyncio
async def test_cb_search_source_drawer_empty_content(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP({
        "mempalace_get_drawer":
            json.dumps({"content": ""}),
    })
    monkeypatch.setattr(sh, "get_mcp", lambda: mcp)
    cb = FakeCb(4242, data="p_srcdr:dreams:r:d1")
    await sh.cb_search_source_drawer(cb)
    assert sh.source_drawer_cache[4242]["chunks"] == [""]


@pytest.mark.asyncio
async def test_cb_search_source_drawer_error(monkeypatch):
    _enable(monkeypatch)

    async def boom(name, params):
        raise RuntimeError("drawer down")

    mcp = FakeMCP({})
    mcp.call_tool = boom
    monkeypatch.setattr(sh, "get_mcp", lambda: mcp)
    cb = FakeCb(4242, data="p_srcdr:dreams:r:d1")
    await sh.cb_search_source_drawer(cb)
    assert "Ошибка" in cb.message.edits[0][0]


@pytest.mark.asyncio
async def test_cb_search_source_drawer_short_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="p_srcdr:dreams:r")
    await sh.cb_search_source_drawer(cb)
    assert getattr(cb.message, "edits", []) == []


# ---------- _render_source_drawer_page ----------


@pytest.mark.asyncio
async def test_render_source_drawer_page_first(monkeypatch):
    _enable(monkeypatch)
    sh.source_drawer_cache[4242] = {"chunks": ["a" * 100, "b" * 100], "wing": "w", "room": "r"}
    edits = []
    await sh._render_source_drawer_page(_edits(edits), 4242, 0)
    assert edits[0][0] == "a" * 100
    assert edits[0][2] is not None
    markup_text = _markup_texts(edits[0][2])
    assert "▶️ Далее" in markup_text
    assert "1/2" in markup_text
    assert "◀️ Назад|" not in markup_text and markup_text.count("◀️") == 1


@pytest.mark.asyncio
async def test_render_source_drawer_page_middle(monkeypatch):
    _enable(monkeypatch)
    sh.source_drawer_cache[4242] = {"chunks": ["a", "b", "c"], "wing": "w", "room": "r"}
    edits = []
    await sh._render_source_drawer_page(_edits(edits), 4242, 1)
    assert edits[0][0] == "b"
    markup_text = _markup_texts(edits[0][2])
    assert "◀️ Назад" in markup_text
    assert "▶️ Далее" in markup_text
    assert "2/3" in markup_text


def _markup_texts(markup):
    if markup is None:
        return ""
    texts = []
    for row in markup.inline_keyboard:
        for btn in row:
            texts.append(btn.text)
    return "|".join(texts)


@pytest.mark.asyncio
async def test_render_source_drawer_page_stale(monkeypatch):
    _enable(monkeypatch)
    edits = []
    await sh._render_source_drawer_page(_edits(edits), 4242, 0)
    assert "устарели" in edits[0][0]


@pytest.mark.asyncio
async def test_render_source_drawer_page_bad_index(monkeypatch):
    _enable(monkeypatch)
    sh.source_drawer_cache[4242] = {"chunks": ["a"], "wing": "w", "room": "r"}
    edits = []
    await sh._render_source_drawer_page(_edits(edits), 4242, 5)
    assert "устарели" in edits[0][0]


# ---------- pagination / misc callbacks ----------


@pytest.mark.asyncio
async def test_cb_search_source_drawer_page(monkeypatch):
    _enable(monkeypatch)
    sh.source_drawer_cache[4242] = {"chunks": ["первая", "вторая"], "wing": "w", "room": "r"}
    cb = FakeCb(4242, data="p_srcdrpg:1")
    await sh.cb_search_source_drawer_page(cb)
    assert any("вторая" in e[0] for e in cb.message.edits)


@pytest.mark.asyncio
async def test_cb_search_source_drawer_page_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="p_srcdrpg:1")
    await sh.cb_search_source_drawer_page(cb)
    assert any("устарели" in e[0] for e in cb.message.edits)


@pytest.mark.asyncio
async def test_cb_search_source_drawer_page_noop(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="p_srcdrpg_noop")
    await sh.cb_search_source_drawer_page_noop(cb)
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_search_source_all_drawers(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP({
        "mempalace_list_drawers":
            json.dumps({"drawers": [{"drawer_id": "d", "content": "x"}], "count": 1}),
    })
    monkeypatch.setattr(sh, "get_mcp", lambda: mcp)
    cb = FakeCb(4242, data="p_srcroom:w:r")
    await sh.cb_search_source_all_drawers(cb)
    assert any("Записи в w/r" in e[0] for e in cb.message.edits)


@pytest.mark.asyncio
async def test_cb_search_source_all_drawers_short(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="p_srcroom:w")
    await sh.cb_search_source_all_drawers(cb)
    assert getattr(cb.message, "edits", []) == []


@pytest.mark.asyncio
async def test_cb_search_source_back(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCP({
        "mempalace_list_drawers":
            json.dumps({"drawers": [{"drawer_id": "d", "content": "x"}], "count": 1}),
    })
    monkeypatch.setattr(sh, "get_mcp", lambda: mcp)
    cb = FakeCb(4242, data="p_srcback:w:r")
    await sh.cb_search_source_back(cb)
    assert any("Записи в w/r" in e[0] for e in cb.message.edits)


@pytest.mark.asyncio
async def test_cb_search_source_back_short(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="p_srcback:w")
    await sh.cb_search_source_back(cb)
    assert getattr(cb.message, "edits", []) == []


@pytest.mark.asyncio
async def test_cb_search_source_open_no_data_attr(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="p_src:1")
    cb.data = None
    await sh.cb_search_source_open(cb)
    assert getattr(cb.message, "edits", []) == []
    assert cb.answered == [(None, None)]


@pytest.mark.asyncio
async def test_cb_search_source_drawer_no_data_attr(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="p_srcdr:dreams:r:d1")
    cb.data = None
    await sh.cb_search_source_drawer(cb)
    assert getattr(cb.message, "edits", []) == []


@pytest.mark.asyncio
async def test_cb_search_source_drawer_page_no_data_attr(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="p_srcdrpg:1")
    cb.data = None
    await sh.cb_search_source_drawer_page(cb)
    assert getattr(cb.message, "edits", []) == []


@pytest.mark.asyncio
async def test_cb_search_source_all_drawers_no_data_attr(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="p_srcroom:w:r")
    cb.data = None
    await sh.cb_search_source_all_drawers(cb)
    assert getattr(cb.message, "edits", []) == []


@pytest.mark.asyncio
async def test_cb_search_source_back_no_data_attr(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(4242, data="p_srcback:w:r")
    cb.data = None
    await sh.cb_search_source_back(cb)
    assert getattr(cb.message, "edits", []) == []
