"""Unit tests for handlers.palace.navigation."""

import asyncio
import base64
import json
import time

import pytest

from handlers.palace import navigation as nav


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
    def __init__(self, uid=4242, data="", message=None):
        self.from_user = FakeUser(uid)
        self.data = data
        self.message = message or FakeMessage(uid)
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
    from handlers.palace import shared as sh

    nav._drawer_list_state.clear()
    nav._active_drawer.clear()
    nav._room_callback_map.clear()
    nav._wing_callback_map.clear()
    for key in (
        "_pending_mcp_input", "_read_state", "_room_session", "_wing_cache",
        "_user_context", "_create_tunnel_state",
    ):
        sh.fsm.pop_data(4242, key)
    yield
    nav._drawer_list_state.clear()
    nav._active_drawer.clear()
    nav._room_callback_map.clear()
    nav._wing_callback_map.clear()
    for key in (
        "_pending_mcp_input", "_read_state", "_room_session", "_wing_cache",
        "_user_context", "_create_tunnel_state",
    ):
        sh.fsm.pop_data(4242, key)


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


async def _fake_edit_fail(msg, t, **k):
    return False


# ---------- codec helpers ----------


def test_encode_callback_part_empty():
    assert nav._encode_callback_part("") == ""


def test_encode_decode_roundtrip():
    encoded = nav._encode_callback_part("философия")
    assert encoded
    assert nav._decode_callback_part(encoded) == "философия"


def test_decode_callback_part_empty():
    assert nav._decode_callback_part("") == ""


def test_decode_callback_part_bad_base64():
    assert nav._decode_callback_part("not b64!!") == "not b64!!"


def test_decode_callback_part_bad_json():
    payload = base64.urlsafe_b64encode(b"not json").decode("ascii")
    assert nav._decode_callback_part(payload) == payload


def test_decode_callback_part_not_dict():
    payload = base64.urlsafe_b64encode(json.dumps("строка").encode()).decode("ascii")
    assert nav._decode_callback_part(payload) == payload


def test_build_room_callback_data():
    data = nav._build_room_callback_data("w", "r")
    assert data.startswith("p_rd_room:")
    key = data[len("p_rd_room:"):]
    assert nav._room_callback_map.get(key) == ("w", "r")


def test_build_wing_callback_data():
    data = nav._build_wing_callback_data("крыло")
    assert data.startswith("p_rs_:")
    assert nav._wing_callback_map.get(data[len("p_rs_:"):]) == "крыло"


def test_decode_wing_callback_data_map_hit():
    nav._wing_callback_map["k1"] = "философия"
    assert nav._decode_wing_callback_data("p_rs_:k1") == "философия"


def test_decode_wing_callback_data_map_miss():
    assert nav._decode_wing_callback_data("p_rs_:aaaa") == "aaaa"


def test_decode_room_callback_data_empty():
    assert nav._decode_room_callback_data("") == ("", "")


def test_decode_room_callback_data_map_hit():
    nav._room_callback_map["k2"] = ("w", "r")
    assert nav._decode_room_callback_data("p_rd_room:k2") == ("w", "r")


def test_decode_room_callback_data_legacy_pair():
    data = "p_rd_room:" + nav._encode_callback_part("w") + ":" + nav._encode_callback_part("r")
    assert nav._decode_room_callback_data(data) == ("w", "r")


def test_decode_room_callback_data_legacy_single():
    data = "p_rd_room:" + nav._encode_callback_part("w")
    assert nav._decode_room_callback_data(data) == ("w", "")


def test_decode_room_callback_data_unknown_prefix():
    assert nav._decode_room_callback_data("xxx") == ("", "")


# ---------- cb_nav_menu ----------


def test_cb_nav_menu(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_nav")
    asyncio.run(nav.cb_nav_menu(cb))
    assert cb.answered == [(None, None)]
    text, pm, markup = cb.message.edits[-1]
    assert "Навигация" in text
    assert pm == "Markdown"
    assert _kb_data(markup) == [
        "p_wing", "p_room", "p_unfiled", "p_tax", "p_grf", "p_trv", "p_tun",
        "palace_back", "palace_main_menu",
    ]


# ---------- cb_list_wings ----------


def test_cb_list_wings_dict(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_wings({"alpha": 3, "beta": 10})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_wing")
    asyncio.run(nav.cb_list_wings(cb))
    markup = cb.message.edits[-1][2]
    buttons = [
        b.text for row in markup.inline_keyboard
        for b in row if b.callback_data != "p_nav"
    ]
    assert buttons == ["🪪 beta", "🪪 alpha"]
    assert nav._wing_cache.get(4242) == ["beta", "alpha"]
    data = _kb_data(cb.message.edits[-1][2])
    assert data[0].startswith("p_rs_:")
    assert nav._wing_callback_map.get(data[0][len("p_rs_:"):]) == "beta"
    assert data[-1] == "p_nav"


def test_cb_list_wings_list(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_wings(["a", "b"])])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_wing")
    asyncio.run(nav.cb_list_wings(cb))
    assert nav._wing_cache.get(4242) == ["a", "b"]


def test_cb_list_wings_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_wing")
    asyncio.run(nav.cb_list_wings(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


# ---------- cb_rooms_menu ----------


def test_cb_rooms_menu_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        _json_wings({"wing_a": 5}),
        _json_rooms({"room1": 3, "room2": 1}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_room")
    asyncio.run(nav.cb_rooms_menu(cb))
    text = cb.message.edits[-1][0]
    assert "wing_a" in text
    assert "room1" in text
    data = _kb_data(cb.message.edits[-1][2])
    assert data[0].startswith("p_rd_room:")
    assert data[-1] == "p_nav"


def test_cb_rooms_menu_more_than_five(monkeypatch):
    _enable(monkeypatch)
    rooms = {f"r{i}": i for i in range(7)}
    mcp = FakeMCPSeq([
        _json_wings({"wing_a": 5}),
        _json_rooms(rooms),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_room")
    asyncio.run(nav.cb_rooms_menu(cb))
    assert "… ещё 2" in cb.message.edits[-1][0]


def test_cb_rooms_menu_empty_wing(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        _json_wings({"wing_a": 5}),
        _json_rooms({}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_room")
    asyncio.run(nav.cb_rooms_menu(cb))
    assert "(пусто)" in cb.message.edits[-1][0]


def test_cb_rooms_menu_edit_fail_answer(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        _json_wings({"wing_a": 5}),
        _json_rooms({"room1": 1}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data="p_room")
    asyncio.run(nav.cb_rooms_menu(cb))
    assert cb.message.answers[0][0].startswith("<b>🪪")


def test_cb_rooms_menu_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_room")
    asyncio.run(nav.cb_rooms_menu(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка загрузки комнат: boom"


# ---------- cb_rooms_select ----------


def _wing_data(wing):
    return nav._build_wing_callback_data(wing)


def test_cb_rooms_select_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(nav.cb_rooms_select(cb))
    assert cb.answered == [(None, None)]


def test_cb_rooms_select_short_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_rs_:")
    asyncio.run(nav.cb_rooms_select(cb))
    assert cb.answered == [(None, None)]


def test_cb_rooms_select_success(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        _json_rooms({"комната": 7, "другая": 2}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data=_wing_data("философия"))
    asyncio.run(nav.cb_rooms_select(cb))
    text = cb.message.edits[-1][0]
    assert "Комнаты крыла философия" in text
    btn_texts = [
        b.text for row in cb.message.edits[-1][2].inline_keyboard for b in row
    ]
    assert any("комната" in b for b in btn_texts)
    assert sh._user_context.get(4242) == {
        "wing": "философия", "room": None, "drawer": None,
    }
    data = _kb_data(cb.message.edits[-1][2])
    assert data[0].startswith("p_rd_room:")
    assert data[-1] == "p_wing"


def test_cb_rooms_select_truncated(monkeypatch):
    _enable(monkeypatch)
    rooms = {f"r{i}": 1 for i in range(51)}
    mcp = FakeMCPSeq([_json_rooms(rooms)])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data=_wing_data("w"))
    asyncio.run(nav.cb_rooms_select(cb))
    assert "и ещё 1 комнат" in cb.message.edits[-1][0]


def test_cb_rooms_select_empty_rooms(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_rooms({})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data=_wing_data("w"))
    asyncio.run(nav.cb_rooms_select(cb))
    assert cb.message.edits[-1][0] == "❌ В крыле «w» нет комнат."


def test_cb_rooms_select_empty_edit_fail(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_rooms({})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data=_wing_data("w"))
    asyncio.run(nav.cb_rooms_select(cb))
    assert cb.message.answers[0][0] == "❌ В крыле «w» нет комнат."


def test_cb_rooms_select_error_edit_fail(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("mcp down")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data=_wing_data("w"))
    asyncio.run(nav.cb_rooms_select(cb))
    assert cb.message.answers[0][0] == "❌ Ошибка загрузки комнат: mcp down"


def test_cb_rooms_select_edit_fail_answer(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_rooms({"комната": 1})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data=_wing_data("w"))
    asyncio.run(nav.cb_rooms_select(cb))
    assert cb.message.answers[0][0].startswith("🪪")


# ---------- cb_open_room_drawer ----------


def test_cb_open_room_drawer_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(nav.cb_open_room_drawer(cb))
    assert cb.answered == [(None, None)]


def test_cb_open_room_drawer_empty_pair(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="xxx")
    asyncio.run(nav.cb_open_room_drawer(cb))
    assert cb.answered == [(None, None)]


def test_cb_open_room_drawer_success(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    captured = []

    async def fake_show(edit_func, uid, wing, room, offset):
        captured.append((edit_func, uid, wing, room, offset))

    monkeypatch.setattr(nav, "_show_drawers_page", fake_show)
    cb = FakeCb(data=nav._build_room_callback_data("w", "r"))
    asyncio.run(nav.cb_open_room_drawer(cb))
    assert captured == [(cb.message.edit_text, 4242, "w", "r", 0)]
    assert sh._user_context.get(4242) == {
        "wing": "w", "room": "r", "drawer": None,
    }


# ---------- cb_get_drawer ----------


def test_cb_get_drawer_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(nav.cb_get_drawer(cb))
    assert cb.answered == [(None, None)]


def test_cb_get_drawer_bad_parts(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_gd:w:r")
    asyncio.run(nav.cb_get_drawer(cb))
    assert cb.answered == [(None, None)]


def test_cb_get_drawer_success(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [
            {"closet_name": "запись", "drawer_id": "d1"},
        ]}),
        json.dumps({"content": "полный текст"}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    captured = []

    async def fake_show(cb, uid, text, name, wing, room, idx):
        captured.append((cb, uid, text, name, wing, room, idx))

    monkeypatch.setattr(nav, "_show_drawer_content", fake_show)
    cb = FakeCb(data="p_gd:w:r:запись")
    asyncio.run(nav.cb_get_drawer(cb))
    assert captured == [(cb, 4242, "полный текст", "запись", "w", "r", 0)]
    assert sh._user_context.get(4242) == {
        "wing": "w", "room": "r", "drawer": "запись",
    }
    state = sh.fsm.get_data(4242).get("_read_state")
    assert state["drawer_id"] == "d1"


def test_cb_get_drawer_fallback_search(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [{"closet_name": "другая"}]}),
        '{"found": "данные из поиска"}',
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_gd:w:r:запись")
    asyncio.run(nav.cb_get_drawer(cb))
    text = cb.message.edits[-1][0]
    assert text == "📄 " + '{"found": "данные из поиска"}'


def test_cb_get_drawer_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_gd:w:r:запись")
    asyncio.run(nav.cb_get_drawer(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


# ---------- cb_cross_ai_article ----------


def test_cb_cross_ai_article_no_session(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_cr_ai")
    asyncio.run(nav.cb_cross_ai_article(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия не найдена."


def test_cb_cross_ai_article_no_drawers(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _room_session={"wing": "w", "room": "r"})
    mcp = FakeMCPSeq([json.dumps({"drawers": []})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_cr_ai")
    asyncio.run(nav.cb_cross_ai_article(cb))
    assert cb.message.edits[-1][0] == "❌ Нет записей для создания статьи."


def test_cb_cross_ai_article_success(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _room_session={"wing": "w", "room": "r"})
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [
            {"content_preview": "превью 1"},
            {"content_preview": "превью 2"},
        ]}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)

    async def fake_ai(*a, **k):
        return "готовая статья"

    monkeypatch.setattr(nav, "call_ai_async", fake_ai)
    captured = {}

    async def fake_finalize(uid, edit_func, text, **kwargs):
        captured["text"] = text
        captured["ctx"] = kwargs.get("ctx", {})
        return None

    monkeypatch.setattr("handlers.palace.action_bar.finalize_answer", fake_finalize)
    cb = FakeCb(data="p_cr_ai")
    asyncio.run(nav.cb_cross_ai_article(cb))
    assert captured["text"] == "готовая статья"
    assert captured["ctx"]["parent_cb"] == "p_rdb"


@pytest.mark.parametrize(
    ("engine", "model"),
    [("openai", "gpt-4o"), ("gemini", "gemini-2.5-pro")],
)
def test_cb_cross_ai_article_uses_configured_model(monkeypatch, engine, model):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _room_session={"wing": "w", "room": "r"})
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [{"content_preview": "превью"}]}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "get_current_ai", lambda: (engine, model))
    calls = []

    async def fake_ai(*args, **kwargs):
        calls.append((args, kwargs))
        return "статья"

    monkeypatch.setattr(nav, "call_ai_async", fake_ai)

    async def fake_finalize(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "handlers.palace.action_bar.finalize_answer", fake_finalize,
    )
    asyncio.run(nav.cb_cross_ai_article(FakeCb(data="p_cr_ai")))

    assert calls[0][0][:2] == (engine, model)


def test_cb_cross_ai_article_missing_model_shows_error(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _room_session={"wing": "w", "room": "r"})
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [{"content_preview": "превью"}]}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("", ""))

    async def must_not_call(*args, **kwargs):
        pytest.fail("AI call must not happen without a configured model")

    monkeypatch.setattr(nav, "call_ai_async", must_not_call)
    cb = FakeCb(data="p_cr_ai")
    asyncio.run(nav.cb_cross_ai_article(cb))

    assert "Модель ИИ не настроена" in cb.message.edits[-1][0]
    assert "/settings" in cb.message.edits[-1][0]


def test_cb_cross_ai_article_model_resolution_error_shows_error(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _room_session={"wing": "w", "room": "r"})
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [{"content_preview": "превью"}]}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)

    def broken_model():
        raise RuntimeError("config broken")

    monkeypatch.setattr(nav, "get_current_ai", broken_model)

    async def must_not_call(*args, **kwargs):
        pytest.fail("AI call must not happen without a configured model")

    monkeypatch.setattr(nav, "call_ai_async", must_not_call)
    cb = FakeCb(data="p_cr_ai")
    asyncio.run(nav.cb_cross_ai_article(cb))

    assert "Не удалось определить модель ИИ" in cb.message.edits[-1][0]
    assert "/settings" in cb.message.edits[-1][0]


def test_cb_cross_ai_article_error(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _room_session={"wing": "w", "room": "r"})
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_cr_ai")
    asyncio.run(nav.cb_cross_ai_article(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


def test_cb_cross_ai_article_ai_error_is_shown(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _room_session={"wing": "w", "room": "r"})
    mcp = FakeMCPSeq([json.dumps({"drawers": [{"content_preview": "п"}]})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)

    async def failing_ai(*a, **k):
        raise RuntimeError("ai down")

    monkeypatch.setattr(nav, "call_ai_async", failing_ai)
    cb = FakeCb(data="p_cr_ai")
    asyncio.run(nav.cb_cross_ai_article(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: ai down"


# ---------- cb_continue_read ----------


def test_cb_continue_read(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_cr:0")
    asyncio.run(nav.cb_continue_read(cb))
    assert cb.answered == [
        ("Пагинация обновлена: откройте запись заново (◀️/▶️ под ответом).", True),
    ]


def test_cb_continue_read_noop(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_cr_noop")
    asyncio.run(nav.cb_continue_read_noop(cb))
    assert cb.answered == [(None, None)]


# ---------- cb_taxonomy ----------


def test_cb_taxonomy_dict(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_wings({"a": 1, "b": 9})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tax")
    asyncio.run(nav.cb_taxonomy(cb))
    text = cb.message.edits[-1][0]
    assert "b" in text and "a" in text
    assert nav._wing_cache.get(4242) == ["b", "a"]
    assert _kb_data(cb.message.edits[-1][2])[:2] == ["p_tw_0", "p_tw_1"]


def test_cb_taxonomy_list(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_wings(["a", "b"])])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tax")
    asyncio.run(nav.cb_taxonomy(cb))
    assert "• a" in cb.message.edits[-1][0]


def test_cb_taxonomy_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tax")
    asyncio.run(nav.cb_taxonomy(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


# ---------- cb_taxonomy_wing ----------


def test_cb_taxonomy_wing_bad_idx(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_tw_нецифра")
    asyncio.run(nav.cb_taxonomy_wing(cb))
    assert cb.answered == [(None, None)]


def test_cb_taxonomy_wing_success(monkeypatch):
    _enable(monkeypatch)
    nav._wing_cache[4242] = ["w1"]
    mcp = FakeMCPSeq([_json_rooms({"комната": 2})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tw_0")
    asyncio.run(nav.cb_taxonomy_wing(cb))
    text = cb.message.edits[-1][0]
    assert "Комнаты крыла w1" in text
    assert _kb_data(cb.message.edits[-1][2])[0].startswith("p_rd_room:")


def test_cb_taxonomy_wing_cache_miss_refetch(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        _json_wings({"w1": 5}),
        _json_rooms({"комната": 2}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tw_0")
    asyncio.run(nav.cb_taxonomy_wing(cb))
    assert "w1" in cb.message.edits[-1][0]
    assert nav._wing_cache.get(4242) == ["w1"]


def test_cb_taxonomy_wing_out_of_range(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_wings({"w1": 5})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tw_5")
    asyncio.run(nav.cb_taxonomy_wing(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла. Начните заново."


def test_cb_taxonomy_wing_no_rooms(monkeypatch):
    _enable(monkeypatch)
    nav._wing_cache[4242] = ["w1"]
    mcp = FakeMCPSeq([_json_rooms({})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tw_0")
    asyncio.run(nav.cb_taxonomy_wing(cb))
    assert cb.message.edits[-1][0] == "❌ В крыле «w1» нет комнат."


# ---------- cb_graph ----------


def test_cb_graph_success_with_tunnels(monkeypatch):
    _enable(monkeypatch)
    stats = json.dumps({
        "total_rooms": 10, "tunnel_rooms": 3, "total_edges": 5,
        "rooms_per_wing": {"b": 7, "a": 3},
    })
    mcp = FakeMCPSeq([stats])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_grf")
    asyncio.run(nav.cb_graph(cb))
    text = cb.message.edits[-1][0]
    assert "Крыльев: 2" in text
    assert "Комнат: 10" in text
    assert "b: 7" in text
    assert "p_tl" in _kb_data(cb.message.edits[-1][2])


def test_cb_graph_no_tunnels(monkeypatch):
    _enable(monkeypatch)
    stats = json.dumps({"total_rooms": 0, "tunnel_rooms": 0,
                        "total_edges": 0, "rooms_per_wing": {}})
    mcp = FakeMCPSeq([stats])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_grf")
    asyncio.run(nav.cb_graph(cb))
    assert "p_tl" not in _kb_data(cb.message.edits[-1][2])
    assert "Туннелей: 0" in cb.message.edits[-1][0]


def test_cb_graph_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_grf")
    asyncio.run(nav.cb_graph(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


# ---------- _show_drawers_page ----------


def _capture_finalize(monkeypatch, store):
    async def fake_finalize(uid, edit_func, text, **kwargs):
        store["text"] = text
        store["ctx"] = kwargs.get("ctx", {})
        store["extra_rows"] = kwargs.get("extra_rows", [])
        store["is_html"] = kwargs.get("is_html", False)
        store["title"] = kwargs.get("title", "")
        return None

    monkeypatch.setattr("handlers.palace.action_bar.finalize_answer", fake_finalize)


def test_show_drawers_page_empty(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"drawers": [], "total": 0})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    msg = FakeMessage()
    asyncio.run(nav._show_drawers_page(msg.edit_text, 4242, "w", "r", 0))
    assert "нет записей" in msg.edits[-1][0]
    assert _kb_data(msg.edits[-1][2]) == ["p_nav"]


def test_show_drawers_page_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({
        "drawers": [
            {"closet_name": "запись 1", "content_preview": "превью текста"},
            {"closet_name": "запись 2", "content_preview": ""},
        ],
        "total": 12,
    })])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    msg = FakeMessage()
    asyncio.run(nav._show_drawers_page(msg.edit_text, 4242, "w", "r", 5))
    assert "Записи в w/r" in captured["text"]
    assert "12 записей" in captured["text"]
    assert "запись 1" in captured["text"]
    assert captured["ctx"]["parent_cb"] == "p_nav"
    assert captured["is_html"] is True
    rows = [[b.callback_data for b in row] for row in captured["extra_rows"]]
    assert rows[0] == ["p_rd:0"]
    assert rows[1] == ["p_rd:1"]
    assert "p_rdp:0" in rows[2]
    assert "p_rdp:10" in rows[2]
    assert rows[3] == ["p_room_ai"]
    assert nav._drawer_list_state.get(4242)["offset"] == 5


def test_show_drawers_page_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    msg = FakeMessage()
    asyncio.run(nav._show_drawers_page(msg.edit_text, 4242, "w", "r", 0))
    assert msg.edits[-1][0] == "❌ Ошибка: boom"


# ---------- cb_read_drawer ----------


def _seed_drawer_state(drawers=None):
    nav._drawer_list_state[4242] = {
        "wing": "w", "room": "r", "offset": 0, "total": 1,
        "drawers": drawers or [{"closet_name": "запись", "drawer_id": "d1"}],
    }


def test_cb_read_drawer_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(nav.cb_read_drawer(cb))
    assert cb.answered == [(None, None)]


def test_cb_read_drawer_bad_parts(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_rd")
    asyncio.run(nav.cb_read_drawer(cb))
    assert cb.answered == [(None, None)]


def test_cb_read_drawer_success(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    _seed_drawer_state()
    mcp = FakeMCPSeq([json.dumps({"content": "полный текст записи"})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    captured = {}

    async def fake_show(cb, uid, text, name, wing, room, idx):
        captured["args"] = (cb, uid, text, name, wing, room, idx)

    monkeypatch.setattr(nav, "_show_drawer_content", fake_show)
    cb = FakeCb(data="p_rd:0")
    asyncio.run(nav.cb_read_drawer(cb))
    assert captured["args"] == (cb, 4242, "полный текст записи", "запись", "w", "r", 0)
    state = sh.fsm.get_data(4242).get("_read_state")
    assert state["drawer"] == "запись"
    assert state["full_content"] == "полный текст записи"


def test_cb_read_drawer_string_content(monkeypatch):
    _enable(monkeypatch)
    _seed_drawer_state()
    mcp = FakeMCPSeq([json.dumps("строка-контент")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    captured = {}

    async def fake_show(cb, uid, text, name, wing, room, idx):
        captured["text"] = text

    monkeypatch.setattr(nav, "_show_drawer_content", fake_show)
    cb = FakeCb(data="p_rd:0")
    asyncio.run(nav.cb_read_drawer(cb))
    assert captured["text"] == "строка-контент"


def test_cb_read_drawer_no_state_refetch(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _user_context={"wing": "w", "room": "r"})
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [{"closet_name": "запись", "drawer_id": "d9"}],
                    "count": 1}),
        json.dumps({"content": "текст"}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    captured = {}

    async def fake_show(cb, uid, text, name, wing, room, idx):
        captured["idx"] = idx

    monkeypatch.setattr(nav, "_show_drawer_content", fake_show)
    cb = FakeCb(data="p_rd:0")
    asyncio.run(nav.cb_read_drawer(cb))
    assert captured["idx"] == 0


def test_cb_read_drawer_no_state_no_drawers(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _user_context={"wing": "w", "room": "r"})
    mcp = FakeMCPSeq([json.dumps({"drawers": []})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_rd:0")
    asyncio.run(nav.cb_read_drawer(cb))
    assert cb.message.edits[-1][0] == "❌ Данные не найдены. Откройте комнату заново."


def test_cb_read_drawer_no_state_no_ctx(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_rd:0")
    asyncio.run(nav.cb_read_drawer(cb))
    assert cb.message.edits[-1][0] == "❌ Данные не найдены. Откройте комнату заново."


def test_cb_read_drawer_no_state_edit_fail(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data="p_rd:0")
    asyncio.run(nav.cb_read_drawer(cb))
    assert cb.message.answers[0][0] == "❌ Данные не найдены. Откройте комнату заново."


def test_cb_read_drawer_error(monkeypatch):
    _enable(monkeypatch)
    _seed_drawer_state()
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_rd:0")
    asyncio.run(nav.cb_read_drawer(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


def test_cb_read_drawer_error_edit_fail(monkeypatch):
    _enable(monkeypatch)
    _seed_drawer_state()
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data="p_rd:0")
    asyncio.run(nav.cb_read_drawer(cb))
    assert cb.message.answers[0][0] == "❌ Ошибка: boom"


# ---------- _show_drawer_content ----------


def test_show_drawer_content_success(monkeypatch):
    _enable(monkeypatch)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    cb = FakeCb(data="p_rd:2")
    asyncio.run(nav._show_drawer_content(cb, 4242, "текст", "запись", "w", "r", 2))
    assert captured["text"] == "текст"
    assert captured["ctx"]["parent_cb"] == "p_rdb"
    assert captured["title"] == "📄 запись"
    rows = [[b.callback_data for b in row] for row in captured["extra_rows"]]
    assert rows == [["p_drdel:2"]]


def test_show_drawer_content_empty_text(monkeypatch):
    _enable(monkeypatch)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    cb = FakeCb(data="p_rd:0")
    asyncio.run(nav._show_drawer_content(cb, 4242, "", "", "w", "r", 0))
    assert captured["text"] == "📄 (пустая запись)"


def test_show_drawer_content_edit_fail_answer(monkeypatch):
    _enable(monkeypatch)
    captured = {}
    _capture_finalize(monkeypatch, captured)

    async def fake_finalize(uid, edit_func, text, **kwargs):
        await edit_func("x")
        return None

    monkeypatch.setattr("handlers.palace.action_bar.finalize_answer", fake_finalize)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data="p_rd:0")
    asyncio.run(nav._show_drawer_content(cb, 4242, "текст", "запись", "w", "r", 0))
    assert cb.message.answers[-1][0] == "x"


# ---------- cb_read_drawer_back ----------


def test_cb_read_drawer_back_with_state(monkeypatch):
    _enable(monkeypatch)
    _seed_drawer_state()
    mcp = FakeMCPSeq([json.dumps({"drawers": [
        {"closet_name": "запись", "drawer_id": "d1", "content_preview": "п"},
    ], "total": 1})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    cb = FakeCb(data="p_rdb")
    asyncio.run(nav.cb_read_drawer_back(cb))
    assert "Записи в w/r" in captured["text"]


def test_cb_read_drawer_back_no_state_with_ctx(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _user_context={"wing": "w", "room": "r"})
    mcp = FakeMCPSeq([json.dumps({"drawers": [], "total": 0})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_rdb")
    asyncio.run(nav.cb_read_drawer_back(cb))
    assert "нет записей" in cb.message.edits[-1][0]


def test_cb_read_drawer_back_no_state_no_ctx(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_rdb")
    asyncio.run(nav.cb_read_drawer_back(cb))
    assert cb.message.edits[-1][0] == "❌ Данные не найдены. Откройте комнату заново."


def test_cb_read_drawer_back_no_state_edit_fail(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data="p_rdb")
    asyncio.run(nav.cb_read_drawer_back(cb))
    assert cb.message.answers[0][0] == "❌ Данные не найдены. Откройте комнату заново."


# ---------- cb_drawer_delete ----------


def _seed_read_state(drawer_id="d1"):
    from handlers.palace import shared as sh

    sh.fsm.update_data(4242, _read_state={
        "room": "r", "wing": "w", "drawer": "запись", "drawer_id": drawer_id,
        "source": "", "full_content": "текст", "offset": 0, "idx": 0,
    })


def test_cb_drawer_delete_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(nav.cb_drawer_delete(cb))
    assert cb.answered == [(None, None)]


def test_cb_drawer_delete_no_state(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_drdel:0")
    asyncio.run(nav.cb_drawer_delete(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла. Откройте запись заново."


def test_cb_drawer_delete_no_state_edit_fail(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data="p_drdel:0")
    asyncio.run(nav.cb_drawer_delete(cb))
    assert cb.message.answers[0][0] == "❌ Сессия истекла. Откройте запись заново."


def test_cb_drawer_delete_success(monkeypatch):
    _enable(monkeypatch)
    _seed_read_state()
    cb = FakeCb(data="p_drdel:0")
    asyncio.run(nav.cb_drawer_delete(cb))
    text, _, markup = cb.message.edits[-1]
    assert "Удалить запись" in text
    assert _kb_data(markup) == ["p_drdel_c:0", "p_drdel_x:0"]


def test_cb_drawer_delete_edit_fail(monkeypatch):
    _enable(monkeypatch)
    _seed_read_state()
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data="p_drdel:0")
    asyncio.run(nav.cb_drawer_delete(cb))
    assert cb.message.answers[0][0] == "❌ Не удалось обновить сообщение."


# ---------- cb_drawer_delete_confirm ----------


def test_cb_drawer_delete_confirm_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(nav.cb_drawer_delete_confirm(cb))
    assert cb.answered == [(None, None)]


def test_cb_drawer_delete_confirm_no_state(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_drdel_c:0")
    asyncio.run(nav.cb_drawer_delete_confirm(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла. Откройте запись заново."


def test_cb_drawer_delete_confirm_success(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    _seed_read_state()
    mcp = FakeMCPSeq([json.dumps({"success": True})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_drdel_c:0")
    asyncio.run(nav.cb_drawer_delete_confirm(cb))
    text, _, markup = cb.message.edits[-1]
    assert "Запись удалена" in text
    assert _kb_data(markup) == ["p_rdb"]
    assert sh.fsm.get_data(4242).get("_read_state") is None


def test_cb_drawer_delete_confirm_not_success(monkeypatch):
    _enable(monkeypatch)
    _seed_read_state()
    mcp = FakeMCPSeq([json.dumps({"success": False, "error": "нет прав"})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_drdel_c:0")
    asyncio.run(nav.cb_drawer_delete_confirm(cb))
    assert cb.message.edits[-1][0] == "❌ Не удалось удалить запись: нет прав"


def test_cb_drawer_delete_confirm_mcp_error(monkeypatch):
    _enable(monkeypatch)
    _seed_read_state()
    mcp = FakeMCPSeq([RuntimeError("mcp down")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_drdel_c:0")
    asyncio.run(nav.cb_drawer_delete_confirm(cb))
    assert cb.message.edits[-1][0] == "❌ Не удалось удалить запись: mcp down"


def test_cb_drawer_delete_confirm_error_edit_fail(monkeypatch):
    _enable(monkeypatch)
    _seed_read_state()
    mcp = FakeMCPSeq([RuntimeError("mcp down")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data="p_drdel_c:0")
    asyncio.run(nav.cb_drawer_delete_confirm(cb))
    assert cb.message.answers[0][0] == "❌ Не удалось удалить запись: mcp down"


def test_cb_drawer_delete_confirm_success_edit_fail(monkeypatch):
    _enable(monkeypatch)
    _seed_read_state()
    mcp = FakeMCPSeq([json.dumps({"success": True})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data="p_drdel_c:0")
    asyncio.run(nav.cb_drawer_delete_confirm(cb))
    assert cb.message.answers[0][0] == "🗑️ Запись удалена."


# ---------- cb_drawer_delete_cancel ----------


def test_cb_drawer_delete_cancel_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(nav.cb_drawer_delete_cancel(cb))
    assert cb.answered == [(None, None)]


def test_cb_drawer_delete_cancel_no_state(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_drdel_x:0")
    asyncio.run(nav.cb_drawer_delete_cancel(cb))
    assert cb.message.edits[-1][0] == "❌ Сессия истекла. Откройте запись заново."


def test_cb_drawer_delete_cancel_success(monkeypatch):
    _enable(monkeypatch)
    _seed_read_state()
    captured = {}
    _capture_finalize(monkeypatch, captured)
    cb = FakeCb(data="p_drdel_x:1")
    asyncio.run(nav.cb_drawer_delete_cancel(cb))
    assert captured["text"] == "текст"
    rows = [[b.callback_data for b in row] for row in captured["extra_rows"]]
    assert rows == [["p_drdel:1"]]


# ---------- cb_read_drawer_page ----------


def test_cb_read_drawer_page_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(nav.cb_read_drawer_page(cb))
    assert cb.answered == [(None, None)]


def test_cb_read_drawer_page_success(monkeypatch):
    _enable(monkeypatch)
    _seed_drawer_state()
    captured = []

    async def fake_show(edit_func, uid, wing, room, offset):
        captured.append((uid, wing, room, offset))

    monkeypatch.setattr(nav, "_show_drawers_page", fake_show)
    cb = FakeCb(data="p_rdp:5")
    asyncio.run(nav.cb_read_drawer_page(cb))
    assert captured == [(4242, "w", "r", 5)]


def test_cb_read_drawer_page_no_state_with_ctx(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _user_context={"wing": "w", "room": "r"})
    mcp = FakeMCPSeq([json.dumps({"drawers": [{"closet_name": "x"}], "count": 1})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    captured = []

    async def fake_show(edit_func, uid, wing, room, offset):
        captured.append(offset)

    monkeypatch.setattr(nav, "_show_drawers_page", fake_show)
    cb = FakeCb(data="p_rdp:0")
    asyncio.run(nav.cb_read_drawer_page(cb))
    assert captured == [0]


def test_cb_read_drawer_page_no_state_ctx_no_drawers(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _user_context={"wing": "w", "room": "r"})
    mcp = FakeMCPSeq([json.dumps({"drawers": []})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_rdp:0")
    asyncio.run(nav.cb_read_drawer_page(cb))
    assert cb.message.edits[-1][0] == "❌ Данные не найдены. Откройте комнату заново."


def test_cb_read_drawer_page_no_state_no_ctx(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_rdp:0")
    asyncio.run(nav.cb_read_drawer_page(cb))
    assert cb.message.edits[-1][0] == "❌ Данные не найдены. Откройте комнату заново."


# ---------- cb_ask_room_ai ----------


def test_cb_ask_room_ai_no_ctx(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_room_ai")
    asyncio.run(nav.cb_ask_room_ai(cb))
    assert cb.message.edits[-1][0] == "❌ Комната не выбрана. Откройте комнату заново."


def test_cb_ask_room_ai_success(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _user_context={"wing": "w", "room": "r"})
    cb = FakeCb(data="p_room_ai")
    asyncio.run(nav.cb_ask_room_ai(cb))
    assert sh._pending_mcp_input.get(4242) == "ask_room_ai:w:r"
    assert cb.message.answers[0][1] == "Markdown"


# ---------- _answer_room_ai ----------


def test_answer_room_ai_no_drawers(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"drawers": []})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    msg = FakeMessage()
    asyncio.run(nav._answer_room_ai(msg, 4242, "w", "r", "вопрос"))
    assert msg.edits[-1][0] == "❌ В комнате w/r нет записей."


def test_answer_room_ai_full_flow(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [
            {"closet_name": "з1", "drawer_id": "d1", "content_preview": "п"},
            {"closet_name": "з2", "drawer_id": "d2", "content_preview": "п"},
        ]}),
        json.dumps({"content": "полный текст 1"}),
        json.dumps({"content": "полный текст 2"}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    answers = ["саммари комнаты", "итоговый ответ"]
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))

    def fake_sync(engine, model, messages):
        return answers.pop(0)

    monkeypatch.setattr("services.ai_engine._sync_ai_call", fake_sync)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    msg = FakeMessage()
    asyncio.run(nav._answer_room_ai(msg, 4242, "w", "r", "какой вопрос?"))
    assert captured["text"] == "итоговый ответ"
    assert captured["ctx"]["parent_cb"] == "p_rdb"
    assert "Ответ по комнате w/r" in captured["title"]
    assert any("Составляю саммари" in t for t, _, _ in msg.edits)
    assert any("Анализирую саммари" in t for t, _, _ in msg.edits)


def test_answer_room_ai_empty_summary_uses_text(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [{"closet_name": "з1", "drawer_id": "d1"}]}),
        json.dumps({"content": "контент"}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    answers = ["", "ответ"]
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))
    monkeypatch.setattr("services.ai_engine._sync_ai_call",
                        lambda *a: answers.pop(0))
    captured = {}
    _capture_finalize(monkeypatch, captured)
    msg = FakeMessage()
    asyncio.run(nav._answer_room_ai(msg, 4242, "w", "r", "вопрос"))
    assert "контент" in captured["text"] or captured["text"] == "ответ"


def test_answer_room_ai_many_drawers(monkeypatch):
    _enable(monkeypatch)
    drawers = [{"closet_name": f"з{i}", "drawer_id": f"d{i}"} for i in range(16)]
    seq = [json.dumps({"drawers": drawers})]
    seq += [json.dumps({"content": "текст"}) for _ in range(15)]
    mcp = FakeMCPSeq(seq)
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    prompts = []

    def fake_sync(engine, model, messages):
        prompts.append(messages[1]["content"])
        return "s" if len(prompts) == 1 else "ответ"

    monkeypatch.setattr("services.ai_engine._sync_ai_call", fake_sync)
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))
    captured = {}
    _capture_finalize(monkeypatch, captured)
    msg = FakeMessage()
    asyncio.run(nav._answer_room_ai(msg, 4242, "w", "r", "вопрос"))
    assert "и ещё 1 записей" in prompts[0]


def test_answer_room_ai_long_content_truncated(monkeypatch):
    _enable(monkeypatch)
    long_text = "x" * 40000
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [{"closet_name": "з1", "drawer_id": "d1"}]}),
        json.dumps({"content": long_text}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    prompts = []

    def fake_sync(engine, model, messages):
        prompts.append(messages[1]["content"])
        return "s" if len(prompts) == 1 else "ответ"

    monkeypatch.setattr("services.ai_engine._sync_ai_call", fake_sync)
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))
    captured = {}
    _capture_finalize(monkeypatch, captured)
    msg = FakeMessage()
    asyncio.run(nav._answer_room_ai(msg, 4242, "w", "r", "вопрос"))
    assert "(контент сокращён из-за длины)" in prompts[0]


def test_answer_room_ai_drawer_fetch_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [
            {"closet_name": "з1", "drawer_id": "d1", "content_preview": "превью"},
        ]}),
        RuntimeError("get fail"),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    prompts = []

    def fake_sync(engine, model, messages):
        prompts.append(messages[1]["content"])
        return "s" if len(prompts) == 1 else "ответ"

    monkeypatch.setattr("services.ai_engine._sync_ai_call", fake_sync)
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))
    captured = {}
    _capture_finalize(monkeypatch, captured)
    msg = FakeMessage()
    asyncio.run(nav._answer_room_ai(msg, 4242, "w", "r", "вопрос"))
    assert "превью" in prompts[0]


def test_answer_room_ai_drawer_no_id(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({
        "drawers": [{"closet_name": "з1", "content_preview": "превью без id"}],
    })])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    prompts = []

    def fake_sync(engine, model, messages):
        prompts.append(messages[1]["content"])
        return "s" if len(prompts) == 1 else "ответ"

    monkeypatch.setattr("services.ai_engine._sync_ai_call", fake_sync)
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))
    captured = {}
    _capture_finalize(monkeypatch, captured)
    msg = FakeMessage()
    asyncio.run(nav._answer_room_ai(msg, 4242, "w", "r", "вопрос"))
    assert "превью без id" in prompts[0]


def test_answer_room_ai_with_web_summary(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _user_context={"_room_summary": "готовая саммари"})

    async def fake_search(query, **kwargs):
        return ["веб-результат"]

    monkeypatch.setattr("services.web_search.search_web", fake_search)
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))
    monkeypatch.setattr("services.ai_engine._sync_ai_call",
                        lambda *a: "веб-ответ")
    captured = {}
    _capture_finalize(monkeypatch, captured)
    msg = FakeMessage()
    asyncio.run(nav._answer_room_ai(msg, 4242, "w", "r", "вопрос", with_web=True))
    assert captured["text"] == "веб-ответ"
    assert any("Ищу в интернете" in t for t, _, _ in msg.edits)


def test_answer_room_ai_with_web_no_summary(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _user_context={})
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [{"closet_name": "з1", "drawer_id": "d1"}]}),
        json.dumps({"content": "контент"}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    answers = ["саммари", "ответ"]
    monkeypatch.setattr("services.ai_engine._sync_ai_call",
                        lambda *a: answers.pop(0))
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))
    captured = {}
    _capture_finalize(monkeypatch, captured)
    msg = FakeMessage()
    asyncio.run(nav._answer_room_ai(msg, 4242, "w", "r", "вопрос", with_web=True))
    assert captured["text"] == "ответ"


def test_answer_room_ai_keeps_event_loop_responsive(monkeypatch, heartbeat):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [{"closet_name": "з1", "drawer_id": "d1"}]}),
        json.dumps({"content": "контент"}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))

    def slow_sync(*a, **k):
        time.sleep(0.03)
        return "ответ"

    monkeypatch.setattr("services.ai_engine._sync_ai_call", slow_sync)
    _capture_finalize(monkeypatch, {})
    msg = FakeMessage()

    async def scenario():
        async with heartbeat(interval=0.005) as hb:
            await nav._answer_room_ai(msg, 4242, "w", "r", "вопрос")
        return hb.ticks

    ticks = asyncio.run(scenario())
    assert ticks >= 1


def test_answer_room_ai_timeout_replaces_status(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [{"closet_name": "з1", "drawer_id": "d1"}]}),
        json.dumps({"content": "контент"}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))

    async def timed_out(*a, **k):
        raise nav.AITimeoutError("too slow")

    monkeypatch.setattr("services.summary_service.call_ai_async", timed_out)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    msg = FakeMessage()
    asyncio.run(nav._answer_room_ai(msg, 4242, "w", "r", "вопрос"))
    assert msg.edits[-1][0] == "⏱️ ИИ не ответил вовремя. Попробуйте ещё раз."
    assert "text" not in captured


def test_answer_room_ai_error_replaces_status(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [{"closet_name": "з1", "drawer_id": "d1"}]}),
        json.dumps({"content": "контент"}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))

    async def failing_ai(*a, **k):
        raise RuntimeError("ai down")

    monkeypatch.setattr("services.summary_service.call_ai_async", failing_ai)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    msg = FakeMessage()
    asyncio.run(nav._answer_room_ai(msg, 4242, "w", "r", "вопрос"))
    assert msg.edits[-1][0] == "❌ Ошибка ИИ: ai down"
    assert "text" not in captured


def test_answer_room_ai_step2_error_replaces_analysis_status(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        json.dumps({"drawers": [{"closet_name": "з1", "drawer_id": "d1"}]}),
        json.dumps({"content": "контент"}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))

    async def fake_summary(*a, **k):
        return "саммари"

    async def failing_ai(*a, **k):
        raise RuntimeError("second call down")

    monkeypatch.setattr("services.summary_service.call_ai_async", fake_summary)
    monkeypatch.setattr(nav, "call_ai_async", failing_ai)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    msg = FakeMessage()
    asyncio.run(nav._answer_room_ai(msg, 4242, "w", "r", "вопрос"))
    assert msg.edits[-1][0] == "❌ Ошибка ИИ: second call down"
    assert "text" not in captured


def test_answer_room_ai_with_web_error_replaces_web_status(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _user_context={"_room_summary": "готовая саммари"})

    async def fake_search(query, **kwargs):
        return ["веб-результат"]

    async def timed_out(*a, **k):
        raise nav.AITimeoutError("too slow")

    monkeypatch.setattr("services.web_search.search_web", fake_search)
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))
    monkeypatch.setattr(nav, "call_ai_async", timed_out)
    captured = {}
    _capture_finalize(monkeypatch, captured)
    msg = FakeMessage()
    asyncio.run(nav._answer_room_ai(msg, 4242, "w", "r", "вопрос", with_web=True))
    assert msg.edits[-1][0] == "⏱️ ИИ не ответил вовремя. Попробуйте ещё раз."
    assert "text" not in captured


# ---------- cb_room_ai_web ----------


def test_cb_room_ai_web_no_question(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_room_ai_web")
    asyncio.run(nav.cb_room_ai_web(cb))
    assert cb.message.answers[0][0] == "❌ Нет сохранённого вопроса. Задайте вопрос заново."


def test_cb_room_ai_web_success(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _user_context={
        "_last_ai_question": "вопрос", "wing": "w", "room": "r",
    })
    captured = []

    async def fake_answer(msg, uid, wing, room, question, with_web):
        captured.append((uid, wing, room, question, with_web))

    monkeypatch.setattr(nav, "_answer_room_ai", fake_answer)
    cb = FakeCb(data="p_room_ai_web")
    asyncio.run(nav.cb_room_ai_web(cb))
    assert captured == [(4242, "w", "r", "вопрос", True)]
    assert cb.message.answers[0][0] == "🌐 Ищу в интернете и уточняю ответ..."


# ---------- traverse ----------


def test_cb_traverse_menu(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_trv")
    asyncio.run(nav.cb_traverse_menu(cb))
    assert _kb_data(cb.message.edits[-1][2]) == ["p_trv_manual", "p_wing", "p_nav"]


def test_cb_traverse_manual(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    cb = FakeCb(data="p_trv_manual")
    asyncio.run(nav.cb_traverse_manual(cb))
    assert sh._pending_mcp_input.get(4242) == "traverse_start"
    assert "Пример:" in cb.message.edits[-1][0]


def test_cb_traverse_step_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(nav.cb_traverse_step(cb))
    assert cb.answered == [(None, None)]


def test_cb_traverse_step_success(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_tr_:5")
    asyncio.run(nav.cb_traverse_step(cb))
    assert cb.answered == [(None, None), ("🔀 Шаг 5", None)]


# ---------- cb_tunnels_menu ----------


def test_cb_tunnels_menu(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_tun")
    asyncio.run(nav.cb_tunnels_menu(cb))
    assert _kb_data(cb.message.edits[-1][2]) == [
        "p_tl", "p_tb", "p_to", "p_tc", "p_tun_ai", "p_nav",
    ]


# ---------- cb_tunnels_list ----------


def _tunnel(tid="t1", label=""):
    return {
        "id": tid, "label": label,
        "source": {"wing": "w1", "room": "r1"},
        "target": {"wing": "w2", "room": "r2"},
    }


def test_cb_tunnels_list_empty(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq(["[]"])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tl")
    asyncio.run(nav.cb_tunnels_list(cb))
    assert cb.message.edits[-1][0] == "🔗 Туннелей нет."


def test_cb_tunnels_list_success(monkeypatch):
    _enable(monkeypatch)
    tunnels = [_tunnel("t1", label="важная связь"), _tunnel("t2")]
    mcp = FakeMCPSeq([json.dumps({"tunnels": tunnels})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tl")
    asyncio.run(nav.cb_tunnels_list(cb))
    text = cb.message.edits[-1][0]
    assert "w1/r1 ⟷ w2/r2" in text
    assert "важная связь" in text
    assert "[t1]" in text
    data = _kb_data(cb.message.edits[-1][2])
    assert data[0] == "p_tdr:t1"
    assert data[-1] == "p_tun"


def test_cb_tunnels_list_truncated(monkeypatch):
    _enable(monkeypatch)
    tunnels = [_tunnel(str(i)) for i in range(31)]
    mcp = FakeMCPSeq([json.dumps({"tunnels": tunnels})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tl")
    asyncio.run(nav.cb_tunnels_list(cb))
    assert "и ещё 1 туннелей" in cb.message.edits[-1][0]


def test_cb_tunnels_list_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tl")
    asyncio.run(nav.cb_tunnels_list(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


# ---------- cb_tunnels_between ----------


def test_cb_tunnels_between(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    cb = FakeCb(data="p_tb")
    asyncio.run(nav.cb_tunnels_between(cb))
    assert sh._pending_mcp_input.get(4242) == "find_tunnels"
    assert "два крыла" in cb.message.edits[-1][0]


def test_cb_tunnels_between_with_wings(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_wings(["philosophy", "psychology"])])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tb")
    asyncio.run(nav.cb_tunnels_between(cb))
    assert sh._pending_mcp_input.get(4242) == "find_tunnels"
    kb = _kb_data(cb.message.edits[-1][2])
    assert "p_tb_w1:philosophy" in kb
    assert "p_tb_w1:psychology" in kb
    assert "p_tun" in kb


def test_cb_tunnels_between_step2(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_wings(["philosophy", "psychology", "art"])])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tb_w1:philosophy")
    asyncio.run(nav.cb_tunnels_between_step2(cb))
    assert sh._pending_mcp_input.get(4242) == "find_tunnels"
    kb = _kb_data(cb.message.edits[-1][2])
    assert "p_tb_run:philosophy:psychology" in kb
    assert "p_tb_run:philosophy:art" in kb
    assert "p_tb_run:philosophy:-" in kb
    assert "p_tb" in kb
    assert "p_tun" in kb


def test_cb_tunnels_between_run(monkeypatch):
    _enable(monkeypatch)
    calls = []

    async def fake_process(uid, query, edit_func):
        calls.append((uid, query))
        return True

    import handlers.palace
    monkeypatch.setattr(handlers.palace, "process_mcp_text_input", fake_process)
    cb = FakeCb(data="p_tb_run:philosophy:psychology")
    asyncio.run(nav.cb_tunnels_between_run(cb))
    assert calls == [(4242, "philosophy psychology")]


def test_cb_tunnels_menu_cleans_pending(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh._pending_mcp_input[4242] = "find_tunnels"
    cb = FakeCb(data="p_tun")
    asyncio.run(nav.cb_tunnels_menu(cb))
    assert 4242 not in sh._pending_mcp_input


# ---------- cb_traverse_tunnel ----------


def test_cb_traverse_tunnel_empty(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq(["[]"])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_to")
    asyncio.run(nav.cb_traverse_tunnel(cb))
    assert cb.message.edits[-1][0] == "🔗 Туннелей нет для прохода."


def test_cb_traverse_tunnel_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": [_tunnel("t1")]})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_to")
    asyncio.run(nav.cb_traverse_tunnel(cb))
    text, _, markup = cb.message.edits[-1]
    assert "Выберите туннель" in text
    assert _kb_data(markup) == ["p_tow:t1", "p_tun"]


def test_cb_traverse_tunnel_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_to")
    asyncio.run(nav.cb_traverse_tunnel(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


# ---------- cb_tow_step ----------


def test_cb_tow_step_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(nav.cb_tow_step(cb))
    assert cb.answered == [(None, None)]


def test_cb_tow_step_not_found(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": [_tunnel("t1")]})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tow:t9")
    asyncio.run(nav.cb_tow_step(cb))
    assert cb.message.edits[-1][0] == "❌ Туннель не найден."


def test_cb_tow_step_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": [_tunnel("t1", label="метка")]})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tow:t1")
    asyncio.run(nav.cb_tow_step(cb))
    text, _, markup = cb.message.edits[-1]
    assert "От: w1/r1" in text
    assert "До: w2/r2" in text
    assert "метка" in text
    assert _kb_data(markup) == ["p_towa:t1", "p_to"]


def test_cb_tow_step_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tow:t1")
    asyncio.run(nav.cb_tow_step(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


# ---------- cb_tunnel_ai_discuss ----------


def test_cb_tunnel_ai_discuss_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(nav.cb_tunnel_ai_discuss(cb))
    assert cb.answered == [(None, None)]


def test_cb_tunnel_ai_discuss_success(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    cb = FakeCb(data="p_towa:t1")
    asyncio.run(nav.cb_tunnel_ai_discuss(cb))
    assert sh._user_context.get(4242) == {"tunnel_id": "t1"}
    assert sh._pending_mcp_input.get(4242) == "tunnel_discuss"
    assert "Напишите ваш вопрос" in cb.message.answers[0][0]


# ---------- cb_tunnel_create ----------


def test_cb_tunnel_create_success(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_wings({"b": 5, "a": 1})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tc")
    asyncio.run(nav.cb_tunnel_create(cb))
    assert sh.fsm.get_data(4242).get("_create_tunnel_state") == {}
    assert _kb_data(cb.message.edits[-1][2])[:2] == ["p_tcs_b", "p_tcs_a"]


def test_cb_tunnel_create_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tc")
    asyncio.run(nav.cb_tunnel_create(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


# ---------- cb_tunnels_ai ----------


def test_cb_tunnels_ai_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": [_tunnel("t1")]})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))

    async def fake_ai(*a, **k):
        return "анализ туннелей"

    monkeypatch.setattr(nav, "call_ai_async", fake_ai)
    cb = FakeCb(data="p_tun_ai")
    asyncio.run(nav.cb_tunnels_ai(cb))
    assert cb.message.edits[-1][0] == "анализ туннелей"


def test_cb_tunnels_ai_empty(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq(["[]"])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tun_ai")
    asyncio.run(nav.cb_tunnels_ai(cb))
    assert cb.message.edits[-1][0] == "🔗 Нет туннелей для анализа."


def test_cb_tunnels_ai_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tun_ai")
    asyncio.run(nav.cb_tunnels_ai(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


def test_cb_tunnels_ai_ai_error_is_shown(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": [_tunnel("t1")]})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "get_current_ai", lambda: ("ollama", "qwen"))

    async def failing_ai(*a, **k):
        raise RuntimeError("ai down")

    monkeypatch.setattr(nav, "call_ai_async", failing_ai)
    cb = FakeCb(data="p_tun_ai")
    asyncio.run(nav.cb_tunnels_ai(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: ai down"


# ---------- cb_tunnel_detail ----------


def test_cb_tunnel_detail_no_data(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(nav.cb_tunnel_detail(cb))
    assert cb.answered == [(None, None)]


def test_cb_tunnel_detail_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": [_tunnel("t1", label="метка")]})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tdr:t1")
    asyncio.run(nav.cb_tunnel_detail(cb))
    text, _, markup = cb.message.edits[-1]
    assert "Туннель: t1..." in text
    assert "метка" in text
    assert _kb_data(markup) == ["p_towa:t1", "p_tdd:t1", "p_tl"]


def test_cb_tunnel_detail_not_found(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": [_tunnel("t1")]})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tdr:t9")
    asyncio.run(nav.cb_tunnel_detail(cb))
    assert cb.message.edits[-1][0] == "❌ Туннель не найден."


def test_cb_tunnel_detail_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tdr:t1")
    asyncio.run(nav.cb_tunnel_detail(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


# ---------- cb_tunnel_detail_both ----------


def test_cb_tunnel_detail_both_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": [_tunnel("t1")]})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tdrb:t1")
    asyncio.run(nav.cb_tunnel_detail_both(cb))
    text = cb.message.edits[-1][0]
    assert "От: w1/r1" in text
    assert "До: w2/r2" in text


def test_cb_tunnel_detail_both_not_found(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": []})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tdrb:t9")
    asyncio.run(nav.cb_tunnel_detail_both(cb))
    assert cb.message.edits[-1][0] == "❌ Туннель не найден."


def test_cb_tunnel_detail_both_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tdrb:t1")
    asyncio.run(nav.cb_tunnel_detail_both(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


# ---------- cb_tunnel_delete ----------


def test_cb_tunnel_delete(monkeypatch):
    _enable(monkeypatch)
    cb = FakeCb(data="p_tdd:t1")
    asyncio.run(nav.cb_tunnel_delete(cb))
    text, _, markup = cb.message.edits[-1]
    assert "Удалить туннель" in text
    assert _kb_data(markup) == ["p_tddc:t1", "p_tl"]


# ---------- cb_tunnel_delete_confirm ----------


def test_cb_tunnel_delete_confirm_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq(['"удалён"'])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tddc:t1")
    asyncio.run(nav.cb_tunnel_delete_confirm(cb))
    assert cb.message.edits[-1][0] == '"удалён"'


def test_cb_tunnel_delete_confirm_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tddc:t1")
    asyncio.run(nav.cb_tunnel_delete_confirm(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


# ---------- cb_tunnel_follow_a / b ----------


def test_cb_tunnel_follow_a_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": [_tunnel("t1")]})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tfa_:t1")
    asyncio.run(nav.cb_tunnel_follow_a(cb))
    assert "Сторона A" in cb.message.edits[-1][0]
    assert "w1/r1" in cb.message.edits[-1][0]


def test_cb_tunnel_follow_a_not_found(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": []})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tfa_:t9")
    asyncio.run(nav.cb_tunnel_follow_a(cb))
    assert cb.message.edits[-1][0] == "❌ Туннель не найден."


def test_cb_tunnel_follow_b_success(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": [_tunnel("t1")]})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tfb_:t1")
    asyncio.run(nav.cb_tunnel_follow_b(cb))
    assert "Сторона B" in cb.message.edits[-1][0]
    assert "w2/r2" in cb.message.edits[-1][0]


def test_cb_tunnel_follow_b_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tfb_:t1")
    asyncio.run(nav.cb_tunnel_follow_b(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


# ---------- not allowed ----------


@pytest.mark.parametrize("data,handler", [
    ("p_nav", "cb_nav_menu"),
    ("p_wing", "cb_list_wings"),
    ("p_room", "cb_rooms_menu"),
    ("p_rs_:x", "cb_rooms_select"),
    ("p_rd_room:x", "cb_open_room_drawer"),
    ("p_gd:w:r:d", "cb_get_drawer"),
    ("p_cr_ai", "cb_cross_ai_article"),
    ("p_cr:0", "cb_continue_read"),
    ("p_cr_noop", "cb_continue_read_noop"),
    ("p_tax", "cb_taxonomy"),
    ("p_tw_0", "cb_taxonomy_wing"),
    ("p_grf", "cb_graph"),
    ("p_rd:0", "cb_read_drawer"),
    ("p_rdb", "cb_read_drawer_back"),
    ("p_drdel:0", "cb_drawer_delete"),
    ("p_drdel_c:0", "cb_drawer_delete_confirm"),
    ("p_drdel_x:0", "cb_drawer_delete_cancel"),
    ("p_rdp:0", "cb_read_drawer_page"),
    ("p_room_ai", "cb_ask_room_ai"),
    ("p_room_ai_web", "cb_room_ai_web"),
    ("p_trv", "cb_traverse_menu"),
    ("p_trv_manual", "cb_traverse_manual"),
    ("p_tr_:0", "cb_traverse_step"),
    ("p_tun", "cb_tunnels_menu"),
    ("p_tl", "cb_tunnels_list"),
    ("p_tb", "cb_tunnels_between"),
    ("p_to", "cb_traverse_tunnel"),
    ("p_tow:t1", "cb_tow_step"),
    ("p_towa:t1", "cb_tunnel_ai_discuss"),
    ("p_tc", "cb_tunnel_create"),
    ("p_tun_ai", "cb_tunnels_ai"),
    ("p_tdr:t1", "cb_tunnel_detail"),
    ("p_tdrb:t1", "cb_tunnel_detail_both"),
    ("p_tdd:t1", "cb_tunnel_delete"),
    ("p_tddc:t1", "cb_tunnel_delete_confirm"),
    ("p_tfa_:t1", "cb_tunnel_follow_a"),
    ("p_tfb_:t1", "cb_tunnel_follow_b"),
])
def test_navigation_not_allowed(monkeypatch, data, handler):
    _enable(monkeypatch)
    cb = FakeCb(uid=999, data=data)
    asyncio.run(getattr(nav, handler)(cb))
    assert cb.answered == [("❌ Нет доступа", True)]


# ---------- edge coverage ----------


def test_cb_rooms_menu_list_wings(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        _json_wings(["wing_a"]),
        _json_rooms({"room1": 1}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_room")
    asyncio.run(nav.cb_rooms_menu(cb))
    assert "wing_a" in cb.message.edits[-1][0]


def test_cb_taxonomy_wing_list_wings(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([
        _json_wings(["w1"]),
        _json_rooms({"комната": 2}),
    ])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tw_0")
    asyncio.run(nav.cb_taxonomy_wing(cb))
    assert "w1" in cb.message.edits[-1][0]


def test_cross_ai_article_edit_func_called(monkeypatch):
    from handlers.palace import shared as sh

    _enable(monkeypatch)
    sh.fsm.update_data(4242, _room_session={"wing": "w", "room": "r"})
    mcp = FakeMCPSeq([json.dumps({"drawers": [
        {"content_preview": "превью"},
    ]})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)

    async def fake_ai(*a, **k):
        return "статья"

    monkeypatch.setattr(nav, "call_ai_async", fake_ai)
    called = []

    async def fake_finalize(uid, edit_func, text, **kwargs):
        await edit_func("статья-текст")
        called.append(True)
        return None

    monkeypatch.setattr("handlers.palace.action_bar.finalize_answer", fake_finalize)
    cb = FakeCb(data="p_cr_ai")
    asyncio.run(nav.cb_cross_ai_article(cb))
    assert called
    assert cb.message.edits[-1][0] == "статья-текст"


def test_cb_read_drawer_no_content_key(monkeypatch):
    _enable(monkeypatch)
    _seed_drawer_state()
    mcp = FakeMCPSeq([json.dumps({"other": 1})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    captured = {}

    async def fake_show(cb, uid, text, name, wing, room, idx):
        captured["text"] = text

    monkeypatch.setattr(nav, "_show_drawer_content", fake_show)
    cb = FakeCb(data="p_rd:0")
    asyncio.run(nav.cb_read_drawer(cb))
    assert captured["text"] == ""


def test_cb_drawer_delete_confirm_no_state_edit_fail(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data="p_drdel_c:0")
    asyncio.run(nav.cb_drawer_delete_confirm(cb))
    assert cb.message.answers[0][0] == "❌ Сессия истекла. Откройте запись заново."


def test_cb_drawer_delete_confirm_not_success_edit_fail(monkeypatch):
    _enable(monkeypatch)
    _seed_read_state()
    mcp = FakeMCPSeq([json.dumps({"success": False, "error": "нет прав"})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data="p_drdel_c:0")
    asyncio.run(nav.cb_drawer_delete_confirm(cb))
    assert cb.message.answers[0][0] == "❌ Не удалось удалить запись: нет прав"


def test_cb_drawer_delete_cancel_no_state_edit_fail(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data="p_drdel_x:0")
    asyncio.run(nav.cb_drawer_delete_cancel(cb))
    assert cb.message.answers[0][0] == "❌ Сессия истекла. Откройте запись заново."


def test_cb_read_drawer_page_no_state_edit_fail(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(nav, "safe_edit_text", _fake_edit_fail)
    cb = FakeCb(data="p_rdp:0")
    asyncio.run(nav.cb_read_drawer_page(cb))
    assert cb.message.answers[0][0] == "❌ Данные не найдены. Откройте комнату заново."


def test_cb_tunnels_list_no_tid(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": [{
        "source": {"wing": "w1", "room": "r1"},
        "target": {"wing": "w2", "room": "r2"},
    }]})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tl")
    asyncio.run(nav.cb_tunnels_list(cb))
    assert "[t" not in cb.message.edits[-1][0]


def test_cb_tow_step_list_form_no_label(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps([{
        "id": "t1",
        "source": {"wing": "w1", "room": "r1"},
        "target": {"wing": "w2", "room": "r2"},
    }])])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tow:t1")
    asyncio.run(nav.cb_tow_step(cb))
    text = cb.message.edits[-1][0]
    assert "От: w1/r1" in text
    assert "📝" not in text


def test_cb_tunnel_detail_list_form_no_label(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps([{
        "id": "t1",
        "source": {"wing": "w1", "room": "r1"},
        "target": {"wing": "w2", "room": "r2"},
    }])])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tdr:t1")
    asyncio.run(nav.cb_tunnel_detail(cb))
    assert "📝" not in cb.message.edits[-1][0]


def test_cb_tunnel_detail_both_list_form(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps([{
        "id": "t1",
        "source": {"wing": "w1", "room": "r1"},
        "target": {"wing": "w2", "room": "r2"},
    }])])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tdrb:t1")
    asyncio.run(nav.cb_tunnel_detail_both(cb))
    assert "От: w1/r1" in cb.message.edits[-1][0]


def test_cb_tunnel_follow_a_list_form(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps([{
        "id": "t1",
        "source": {"wing": "w1", "room": "r1"},
        "target": {"wing": "w2", "room": "r2"},
    }])])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tfa_:t1")
    asyncio.run(nav.cb_tunnel_follow_a(cb))
    assert "w1/r1" in cb.message.edits[-1][0]


def test_cb_tunnel_follow_b_list_form(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps([{
        "id": "t1",
        "source": {"wing": "w1", "room": "r1"},
        "target": {"wing": "w2", "room": "r2"},
    }])])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tfb_:t1")
    asyncio.run(nav.cb_tunnel_follow_b(cb))
    assert "w2/r2" in cb.message.edits[-1][0]


def test_cb_tunnel_follow_a_error(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([RuntimeError("boom")])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tfa_:t1")
    asyncio.run(nav.cb_tunnel_follow_a(cb))
    assert cb.message.edits[-1][0] == "❌ Ошибка: boom"


def test_cb_tunnel_create_list_wings(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([_json_wings(["a", "b"])])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tc")
    asyncio.run(nav.cb_tunnel_create(cb))
    assert _kb_data(cb.message.edits[-1][2])[:2] == ["p_tcs_a", "p_tcs_b"]


@pytest.mark.parametrize("data,handler", [
    ("p_tdrb:t1", "cb_tunnel_detail_both"),
    ("p_tdd:t1", "cb_tunnel_delete"),
    ("p_tddc:t1", "cb_tunnel_delete_confirm"),
    ("p_tfa_:t1", "cb_tunnel_follow_a"),
    ("p_tfb_:t1", "cb_tunnel_follow_b"),
])
def test_cb_no_data_guard(monkeypatch, data, handler):
    _enable(monkeypatch)
    cb = FakeCb()
    asyncio.run(getattr(nav, handler)(cb))
    assert cb.answered == [(None, None)]


def test_cb_tunnel_follow_b_not_found(monkeypatch):
    _enable(monkeypatch)
    mcp = FakeMCPSeq([json.dumps({"tunnels": []})])
    monkeypatch.setattr(nav, "get_mcp", lambda: mcp)
    cb = FakeCb(data="p_tfb_:t9")
    asyncio.run(nav.cb_tunnel_follow_b(cb))
    assert cb.message.edits[-1][0] == "❌ Туннель не найден."
