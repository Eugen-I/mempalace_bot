"""Тесты пагинации записи из поиска и чтения полного источника в KG."""
import asyncio

import pytest

from tests.test_action_bar import FakeCallback, FakeMessage, _markup_data, TEST_UID


@pytest.fixture(autouse=True)
def _allow_test_user(monkeypatch):
    import config

    monkeypatch.setattr(config, "ALLOWED_IDS", {TEST_UID})
    yield


def _markup_labels(msg):
    kb = msg.markups[-1]
    if kb is None:
        return []
    return [b.text for row in kb.inline_keyboard for b in row]


def test_render_source_drawer_page_single_chunk(monkeypatch):
    import handlers.search as search

    monkeypatch.setattr(
        search, "source_drawer_cache",
        {TEST_UID: {"chunks": ["короткий текст"], "wing": "w1", "room": "r1"}},
    )
    msg = FakeMessage()
    asyncio.run(search._render_source_drawer_page(msg.edit_text, TEST_UID, 0))
    data = _markup_data(msg)
    assert "короткий текст" in msg.edited[-1]
    assert not any(d.startswith("p_srcdrpg:") and "noop" not in d for d in data)
    assert "p_srcback:w1:r1" in data
    assert any("1/1" in l for l in _markup_labels(msg))


def test_render_source_drawer_page_multi_chunk_navigation(monkeypatch):
    import handlers.search as search

    chunks = ["чанк-1", "чанк-2", "чанк-3"]
    monkeypatch.setattr(
        search, "source_drawer_cache",
        {TEST_UID: {"chunks": chunks, "wing": "w1", "room": "r1"}},
    )
    msg = FakeMessage()
    asyncio.run(search._render_source_drawer_page(msg.edit_text, TEST_UID, 1))
    data = _markup_data(msg)
    assert "чанк-2" in msg.edited[-1]
    assert "p_srcdrpg:0" in data
    assert "p_srcdrpg:2" in data
    assert any("2/3" in l for l in _markup_labels(msg))


def test_render_source_drawer_page_out_of_range(monkeypatch):
    import handlers.search as search

    monkeypatch.setattr(
        search, "source_drawer_cache",
        {TEST_UID: {"chunks": ["только"], "wing": "w1", "room": "r1"}},
    )
    msg = FakeMessage()
    asyncio.run(search._render_source_drawer_page(msg.edit_text, TEST_UID, 5))
    assert "устарели" in msg.edited[-1]


def test_cb_search_source_drawer_paginates(monkeypatch):
    import handlers.search as search

    long_text = "абвгд " * 800

    class FakeMCP:
        async def call_tool(self, name, args=None):
            return '{"content": "%s"}' % long_text

    monkeypatch.setattr(search, "get_mcp", lambda: FakeMCP())
    msg = FakeMessage()
    cb = FakeCallback("p_srcdr:w1:r1:drawer-x", msg)
    asyncio.run(search.cb_search_source_drawer(cb))
    assert len(search.source_drawer_cache[TEST_UID]["chunks"]) > 1
    assert any("1/2" in l for l in _markup_labels(msg))


def test_cb_kg_read_back_full_source_paginates(monkeypatch):
    import handlers.palace.action_bar as ab
    from handlers.palace import kg

    full = "текст-источник " * 500
    monkeypatch.setattr(kg, "_read_state", {TEST_UID: {"source": full}})
    msg = FakeMessage()
    cb = FakeCallback("p_krb:f", msg)
    asyncio.run(kg.cb_kg_read_back(cb))
    data = _markup_data(msg)
    assert any(d.startswith("ab_pg:") for d in data)
    answer = ab.get_answer([d for d in data if d.startswith("ab_ai:")][0][6:])
    assert answer is not None
    assert answer.total_pages > 1


def test_cb_kg_read_back_no_state():
    from handlers.palace import kg

    msg = FakeMessage()
    cb = FakeCallback("p_krb:x", msg)
    asyncio.run(kg.cb_kg_read_back(cb))
    assert "Конец записи" in msg.edited[-1]
