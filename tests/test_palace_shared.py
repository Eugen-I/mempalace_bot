"""Unit tests for handlers.palace.shared."""

from types import SimpleNamespace

import pytest

from handlers.palace import shared as sh


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


@pytest.fixture(autouse=True)
def _clean_state():
    for key in (
        "_pending_mcp_input", "_kg_page_data", "_kg_search_data",
        "_kg_add_state", "_save_state", "_wing_cache", "_room_cache",
        "_tunnel_state", "_create_tunnel_state", "_drawer_state",
        "_read_state", "_room_session", "_tunnels_cache", "_user_context",
    ):
        sh.fsm.pop_data(4242, key)
    yield
    for key in (
        "_pending_mcp_input", "_kg_page_data", "_kg_search_data",
        "_kg_add_state", "_save_state", "_wing_cache", "_room_cache",
        "_tunnel_state", "_create_tunnel_state", "_drawer_state",
        "_read_state", "_room_session", "_tunnels_cache", "_user_context",
    ):
        sh.fsm.pop_data(4242, key)


# ---------- _normalize_query ----------


def test_normalize_query_alias():
    assert sh._normalize_query("  Мои Заметки  ") == "my_notes"


def test_normalize_query_alias_room():
    assert sh._normalize_query("Сны") == "dreams"


def test_normalize_query_spaces_to_underscore():
    assert sh._normalize_query("Крыло Комната") == "крыло_комната"


def test_normalize_query_plain():
    assert sh._normalize_query("tech") == "tech"


# ---------- fsm accessors ----------


def test_get_data_default():
    assert sh._get_data(4242, "nope", "default") == "default"


def test_get_data_with_value():
    sh.fsm.update_data(4242, key="value")
    assert sh._get_data(4242, "key") == "value"


def test_set_data():
    sh._set_data(4242, a=1, b=2)
    data = sh.fsm.get_data(4242)
    assert data["a"] == 1
    assert data["b"] == 2


def test_pop_data():
    sh.fsm.update_data(4242, key="value")
    assert sh._pop_data(4242, "key") == "value"
    assert sh._pop_data(4242, "key", "default") == "default"


# ---------- _FsmDict ----------


def test_fsm_dict_set_get_item():
    sh._save_state[4242] = {"text": "x"}
    assert sh._save_state[4242] == {"text": "x"}


def test_fsm_dict_getitem_missing_raises():
    with pytest.raises(KeyError):
        sh._save_state[4242]


def test_fsm_dict_get():
    assert sh._save_state.get(4242) is None
    assert sh._save_state.get(4242, "d") == "d"
    sh._save_state[4242] = {"text": "x"}
    assert sh._save_state.get(4242) == {"text": "x"}


def test_fsm_dict_pop():
    sh._save_state[4242] = {"text": "x"}
    assert sh._save_state.pop(4242) == {"text": "x"}
    assert sh._save_state.pop(4242, "d") == "d"


def test_fsm_dict_contains():
    assert 4242 not in sh._save_state
    sh._save_state[4242] = {"text": "x"}
    assert 4242 in sh._save_state


def test_fsm_dict_setdefault_existing():
    sh._save_state[4242] = {"text": "x"}
    out = sh._save_state.setdefault(4242, {"other": 1})
    assert out == {"text": "x"}
    assert sh._save_state[4242]["text"] == "x"


def test_fsm_dict_setdefault_missing():
    out = sh._save_state.setdefault(4242, {"other": 1})
    assert out == {"other": 1}
    assert sh._save_state[4242] == {"other": 1}


def test_fsm_dict_setdefault_none_default():
    out = sh._save_state.setdefault(4242)
    assert out == {}
    assert sh._save_state[4242] == {}


# ---------- _send_kg_page ----------


def _fake_finalize():
    captured = {}

    async def finalize_answer(uid, edit_func, text, is_html=False, ctx=None,
                              extra_rows=None):
        captured["uid"] = uid
        captured["edit_func"] = edit_func
        captured["text"] = text
        captured["ctx"] = ctx
        captured["extra_rows"] = extra_rows

    return finalize_answer, captured


def test_send_kg_page_no_data(monkeypatch):
    edits = []

    async def edit_func(text, **kw):
        edits.append(text)

    import asyncio

    asyncio.run(sh._send_kg_page(4242, edit_func))
    assert edits == []


def test_send_kg_page_first_page(monkeypatch):
    monkeypatch.setattr(sh, "safe_html_format", lambda t: t)
    fake, captured = _fake_finalize()
    monkeypatch.setattr(
        "handlers.palace.action_bar.finalize_answer", fake,
    )
    facts = [
        {"subject": "s1", "predicate": "p1", "object": "o1",
         "source_closet": "/a/b/file1.md", "valid_from": "2024"},
        {"subject": "s2", "predicate": "p2", "object": "o2"},
        {"subject": "s3", "predicate": "p3", "object": "o3"},
        {"subject": "s4", "predicate": "p4", "object": "o4"},
        {"subject": "s5", "predicate": "p5", "object": "o5"},
        {"subject": "s6", "predicate": "p6", "object": "o6"},
    ]
    sh._kg_page_data[4242] = {"entity": "Энтити", "facts": facts, "page": 0}
    import asyncio

    asyncio.run(sh._send_kg_page(4242, lambda *a, **k: None))
    assert captured["ctx"] == {"entity": "Энтити", "parent_cb": "p_kg"}
    assert "Энтити" in captured["text"]
    assert "(6 фактов)" in captured["text"]
    assert "file1.md" in captured["text"]
    assert "(с 2024)" in captured["text"]
    assert captured["extra_rows"][0][0].callback_data == "p_kgc"


def test_send_kg_page_last_page(monkeypatch):
    monkeypatch.setattr(sh, "safe_html_format", lambda t: t)
    fake, captured = _fake_finalize()
    monkeypatch.setattr(
        "handlers.palace.action_bar.finalize_answer", fake,
    )
    facts = [{"subject": f"s{i}", "predicate": "p", "object": "o"}
             for i in range(6)]
    sh._kg_page_data[4242] = {"entity": "Э", "facts": facts, "page": 1}
    import asyncio

    asyncio.run(sh._send_kg_page(4242, lambda *a, **k: None))
    assert captured["extra_rows"][0][0].callback_data == "p_kgs"


def test_send_kg_page_single_page(monkeypatch):
    monkeypatch.setattr(sh, "safe_html_format", lambda t: t)
    fake, captured = _fake_finalize()
    monkeypatch.setattr(
        "handlers.palace.action_bar.finalize_answer", fake,
    )
    facts = [{"subject": "s1", "predicate": "p", "object": "o"}]
    sh._kg_page_data[4242] = {"entity": "Э", "facts": facts, "page": 0}
    import asyncio

    asyncio.run(sh._send_kg_page(4242, lambda *a, **k: None))
    assert captured["extra_rows"][0][0].callback_data == "p_kgr"
    assert len(captured["extra_rows"]) == 1


def test_send_kg_page_string_facts(monkeypatch):
    monkeypatch.setattr(sh, "safe_html_format", lambda t: t)
    fake, captured = _fake_finalize()
    monkeypatch.setattr(
        "handlers.palace.action_bar.finalize_answer", fake,
    )
    sh._kg_page_data[4242] = {
        "entity": "Э", "facts": ["простой факт", "ещё факт"], "page": 0,
    }
    import asyncio

    asyncio.run(sh._send_kg_page(4242, lambda *a, **k: None))
    assert "• простой факт" in captured["text"]


# ---------- _format_mcp_result ----------


def test_format_mcp_result_not_json():
    import asyncio

    assert asyncio.run(sh._format_mcp_result("сыро")) == "сыро"


def test_format_mcp_result_empty():
    import asyncio

    assert asyncio.run(sh._format_mcp_result("")) == ""


def test_format_mcp_result_dict_scalar():
    import asyncio

    out = asyncio.run(sh._format_mcp_result('{"a": 1, "b": "x"}'))
    assert "**a:** 1" in out
    assert "**b:** x" in out


def test_format_mcp_result_dict_nested():
    import asyncio

    out = asyncio.run(sh._format_mcp_result('{"a": {"k1": "v1", "k2": "v2"}}'))
    assert "**a:**" in out
    assert "• k1: v1" in out


def test_format_mcp_result_dict_list():
    import asyncio

    out = asyncio.run(sh._format_mcp_result('{"a": [1, 2]}'))
    assert "• 1" in out
    assert "• 2" in out


def test_format_mcp_result_non_dict_json():
    import asyncio

    out = asyncio.run(sh._format_mcp_result("[1, 2]"))
    assert out == "[1, 2]"


def test_format_mcp_result_invalid():
    import asyncio

    assert asyncio.run(sh._format_mcp_result('{"broken')) == '{"broken'
