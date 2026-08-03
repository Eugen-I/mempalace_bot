"""Тесты ранжирования релевантности в palace_bridge и кнопок «📄 Читать [N]» в /search."""
import asyncio

import pytest

from tests.test_action_bar import FakeMessage, _markup_data, TEST_UID


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


def test_rank_hits_empty():
    from services.palace_bridge import _rank_hits

    assert _rank_hits([]) == []


def test_rank_hits_vector_only_orders_by_distance():
    from services.palace_bridge import _rank_hits

    hits = [
        {"distance": 0.8, "text": "далёкий"},
        {"distance": 0.2, "text": "близкий"},
        {"distance": 0.5, "text": "средний"},
    ]
    ranked = _rank_hits(hits)
    assert [h["text"] for h in ranked] == ["близкий", "средний", "далёкий"]


def test_rank_hits_bm25_dominates_when_max_norm():
    from services.palace_bridge import _rank_hits

    # Сильный лексический релевант = большой bm25, должен победить слабый векторный
    hits = [
        {"distance": 0.1, "bm25_score": 1.0, "text": "векторно близкий, лексически слабый"},
        {"distance": 0.6, "bm25_score": 20.0, "text": "лексически точное совпадение"},
    ]
    ranked = _rank_hits(hits)
    assert ranked[0]["text"] == "лексически точное совпадение"


def test_rank_hits_considers_both_signals():
    from services.palace_bridge import _rank_hits

    # h1: близко по vector и норм bm25; h2: далеко и bm25 маленький
    hits = [
        {"distance": 0.7, "bm25_score": 2.0, "text": "a"},
        {"distance": 0.1, "bm25_score": 5.0, "text": "b"},
    ]
    assert _rank_hits(hits)[0]["text"] == "b"


def test_rank_hits_halfers_tie():
    """Граничное: hits без distance/без bm25 не падают."""
    from services.palace_bridge import _rank_hits

    hits = [
        {"distance": 0.3},
        {"bm25_score": 4.0},
        {},
    ]
    ranked = _rank_hits(hits)
    assert len(ranked) == 3
    assert ranked[-1] == {}


def test_search_api_ranks_and_limits(monkeypatch):
    """_search_via_api возвращает top-N по релевантности, а не как пришли."""
    import asyncio
    import sys
    import types

    import services.palace_bridge as pb

    searcher_mod = types.ModuleType("mempalace.searcher")
    searcher_mod.search_memories = lambda *a, **_k: {"results": [
        {"distance": 0.9, "bm25_score": 0.0, "text": "нерелевантный"},
        {"distance": 0.1, "bm25_score": 5.0, "text": "топ-1"},
        {"distance": 0.6, "bm25_score": 3.0, "text": "топ-2"},
        {"distance": 0.9, "bm25_score": 1.0, "text": "топ-3"},
    ]}
    config_mod = types.ModuleType("mempalace.config")
    config_mod.MempalaceConfig = lambda: types.SimpleNamespace(
        palace_path="/tmp/x", collection_name="cola",
    )
    monkeypatch.setitem(sys.modules, "mempalace.searcher", searcher_mod)
    monkeypatch.setitem(sys.modules, "mempalace.config", config_mod)

    def _fake_executor(fn, *args):
        f = asyncio.Future()
        f.set_result(fn(*args))
        return f

    class FakeLoop:
        def run_in_executor(self, executor, fn, *args):
            return _fake_executor(fn, *args)

    monkeypatch.setattr(pb.asyncio, "get_event_loop", lambda: FakeLoop())

    result = asyncio.run(pb._search_via_api("хелло", limit=3))
    assert "топ-1" in result["text"]
    assert "топ-2" in result["text"]
    assert "нерелевантный" not in result["text"]
    assert len(result["sources"]) == 2


def test_rank_bm25_max_zero_all_ones():
    """Граница: все bm25 — None, только distance ранжирует."""
    from services.palace_bridge import _rank_hits

    hits = [
        {"distance": 0.2},
        {"distance": 0.8},
    ]
    assert _rank_hits(hits)[0]["distance"] == 0.2


def test_cmd_search_shows_source_buttons(monkeypatch):
    """cmd_search выводит кнопки «📄 Читать [N]» и кэширует источники."""
    import handlers.search as search

    sources = [
        {"id": 1, "wing": "dreams", "room": "коридор", "file": "", "score": 0.9},
        {"id": 2, "wing": "projects", "room": "идеи", "file": "", "score": 0.7},
    ]

    async def fake_search(text, limit=5, wing=""):
        return "Результат по запросу", sources

    monkeypatch.setattr(search, "search_palace_with_sources", fake_search)
    search.search_result_cache.clear()

    class Msg(FakeMessage):
        def __init__(self):
            super().__init__()
            self.text = "/search сны"
            self.from_user = type("U", (), {"id": TEST_UID})()

        async def delete(self):
            self.deleted = True

    msg = Msg()

    async def _main():
        await search.cmd_search(msg)

    asyncio.run(_main())

    data = _markup_data(msg, -1)
    assert "p_src:1" in data
    assert "p_src:2" in data
    labels = _markup_labels(msg)
    assert any("Читать [1]" in t for t in labels)
    assert any("Читать [2]" in t for t in labels)
    assert any("Новый поиск" in t for t in labels)
    assert search.search_result_cache.get(TEST_UID) == sources


def test_cmd_search_no_results_no_buttons(monkeypatch):
    """Разграничение: пустой результат — без кнопок."""
    import handlers.search as search

    async def fake_search(text, limit=5, wing=""):
        return "", []

    monkeypatch.setattr(search, "search_palace_with_sources", fake_search)
    search.search_result_cache.clear()

    class Msg(FakeMessage):
        def __init__(self):
            super().__init__()
            self.text = "/search несуществующаятема"
            self.from_user = type("U", (), {"id": TEST_UID})()

        async def delete(self):
            self.deleted = True

    msg = Msg()

    async def _send():
        await search.cmd_search(msg)

    asyncio.run(_send())

    assert any("Ничего не найдено" in e for e in msg.edited)
    assert not search.search_result_cache.get(TEST_UID)
