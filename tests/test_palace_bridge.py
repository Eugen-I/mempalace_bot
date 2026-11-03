"""Unit tests for services.palace_bridge.

Covers search wrappers (circuit breaker, fallbacks), hit ranking, CLI/API
search paths, tunnel-following, KG search and exports.
"""

import json
import sys

import pytest

import services.palace_bridge as pb
import services.palace_mcp as palace_mcp
from services.circuit_breaker import (
    CircuitBreakerOpenError,
    get_palace_circuit_breaker,
)


@pytest.fixture
def palace_cb():
    cb = get_palace_circuit_breaker()
    cb.reset()
    return cb


# ---------- search_palace_context ----------


@pytest.mark.asyncio
async def test_search_palace_context_happy_path(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing="", room=""):
        return {
            "text": "Запись о Наполеоне",
            "sources": [{
                "id": 1, "wing": "history", "room": "figures",
                "file": "", "score": 0.42,
            }],
        }

    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    out = await pb.search_palace_context("наполеон")
    assert "ЛИЧНЫЕ ЗАПИСИ" in out
    assert "Запись о Наполеоне" in out
    assert "ИСТОЧНИКИ" in out
    assert "[1] history/figures (score: 0.420)" in out


@pytest.mark.asyncio
async def test_search_palace_context_no_sources(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing="", room=""):
        return {"text": "просто текст", "sources": []}

    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    out = await pb.search_palace_context("спросить")
    assert "просто текст" in out
    assert "ИСТОЧНИКИ" not in out


@pytest.mark.asyncio
async def test_search_palace_context_empty_text(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing="", room=""):
        return {"text": "", "sources": []}

    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    assert await pb.search_palace_context("ничего") == ""


@pytest.mark.asyncio
async def test_search_palace_context_source_file_only(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing="", room=""):
        return {
            "text": "из файла",
            "sources": [{
                "id": 2, "wing": "", "room": "", "file": "note.md", "score": 0.1,
            }],
        }

    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    out = await pb.search_palace_context("файл")
    assert "[2] note.md (score: 0.100)" in out


@pytest.mark.asyncio
async def test_search_palace_context_circuit_breaker_open(monkeypatch, palace_cb):
    async def boom(q, limit=5, wing="", room=""):
        raise CircuitBreakerOpenError("open")

    monkeypatch.setattr(pb, "_search_palace_context_impl", boom)
    assert await pb.search_palace_context("x") == ""


@pytest.mark.asyncio
async def test_search_palace_context_generic_error(monkeypatch, palace_cb):
    async def boom(q, limit=5, wing="", room=""):
        raise RuntimeError("db gone")

    monkeypatch.setattr(pb, "_search_palace_context_impl", boom)
    assert await pb.search_palace_context("x") == ""


# ---------- search_palace_with_sources ----------


@pytest.mark.asyncio
async def test_search_palace_with_sources_happy(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing="", room=""):
        return {"text": "текст", "sources": [{"id": 3, "score": 0.5}]}

    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    text, sources = await pb.search_palace_with_sources("запрос")
    assert text == "текст"
    assert sources == [{"id": 3, "score": 0.5}]


@pytest.mark.asyncio
async def test_search_palace_with_sources_empty(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing="", room=""):
        return {"text": "", "sources": []}

    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    assert await pb.search_palace_with_sources("x") == ("", [])


@pytest.mark.asyncio
async def test_search_palace_with_sources_error(monkeypatch, palace_cb):
    async def boom(*a):
        raise RuntimeError("search died")

    monkeypatch.setattr(pb, "_search_palace_context_impl", boom)
    assert await pb.search_palace_with_sources("q") == ("", [])


@pytest.mark.asyncio
async def test_search_palace_with_sources_circuit_breaker_open(monkeypatch, palace_cb):
    async def boom(*a):
        raise CircuitBreakerOpenError("open")

    monkeypatch.setattr(pb, "_search_palace_context_impl", boom)
    assert await pb.search_palace_with_sources("q") == ("", [])

    async def boom(q, limit=5, wing="", room=""):
        raise ValueError("nope")

    monkeypatch.setattr(pb, "_search_palace_context_impl", boom)
    assert await pb.search_palace_with_sources("x") == ("", [])


@pytest.mark.asyncio
async def test_search_palace_with_sources_text_without_sources(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing="", room=""):
        return {"text": "только текст", "sources": []}

    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    assert await pb.search_palace_with_sources("q") == ("только текст", [])


@pytest.mark.asyncio
async def test_public_search_wrappers_share_impl(monkeypatch, palace_cb):
    calls = []

    async def fake_impl(q, limit=5, wing="", room=""):
        calls.append((q, limit, wing, room))
        return {"text": "текст", "sources": []}

    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    await pb.search_palace_context("q1", limit=3, wing="w1", room="r1")
    await pb.search_palace_with_sources("q2", limit=4, wing="w2", room="r2")

    assert calls == [
        ("q1", 3, "w1", "r1"),
        ("q2", 4, "w2", "r2"),
    ]


def test_format_sources_block_golden():
    block = pb._format_sources_block([
        {"id": 1, "wing": "w", "room": "r", "file": "", "score": 0.42},
        {"id": 2, "wing": "", "room": "", "file": "note.md", "score": 0.1},
    ])
    assert block == (
        "--- ИСТОЧНИКИ ---\n"
        "[1] w/r (score: 0.420)\n"
        "[2] note.md (score: 0.100)\n"
        "--- КОНЕЦ ИСТОЧНИКОВ ---\n"
    )


def test_format_sources_block_empty():
    assert pb._format_sources_block([]) == ""


def test_format_context_without_sources():
    assert pb._format_context("текст", []) == (
        "\n--- ЛИЧНЫЕ ЗАПИСИ ИЗ MEMPALACE (Приоритетный источник) ---\n"
        "текст\n"
        "--- КОНЕЦ ЛИЧНЫХ ЗАПИСЕЙ ---\n"
    )


# ---------- _search_palace_context_impl ----------


@pytest.mark.asyncio
async def test_impl_blank_query_returns_empty(monkeypatch):
    assert await pb._search_palace_context_impl("   ") == {"text": "", "sources": []}


@pytest.mark.asyncio
async def test_impl_empty_after_sanitize(monkeypatch):
    async def empty(q, limit=5, wing="", room=""):
        return {"text": "", "sources": []}

    monkeypatch.setattr(pb, "_search_via_api", empty)
    monkeypatch.setattr(pb, "_search_via_cli", empty)
    assert await pb._search_palace_context_impl('""') == {"text": "", "sources": []}


@pytest.mark.asyncio
async def test_impl_uses_api_results(monkeypatch):
    calls = {}

    async def fake_api(q, limit=5, wing="", room=""):
        calls["limit"] = limit
        return {"text": "api hit", "sources": [{"id": 1}]}

    monkeypatch.setattr(pb, "_search_via_api", fake_api)
    out = await pb._search_palace_context_impl('some "quote"', limit=3, wing="w")
    assert out["text"] == "api hit"
    assert calls["limit"] == 3


@pytest.mark.asyncio
async def test_impl_wing_fallback_to_global(monkeypatch):
    calls = []

    async def fake_api(q, limit=5, wing="", room=""):
        calls.append((wing, room))
        if wing:
            return {"text": "", "sources": []}
        return {"text": "global hit", "sources": []}

    monkeypatch.setattr(pb, "_search_via_api", fake_api)
    out = await pb._search_palace_context_impl("запрос", wing="my_notes")
    assert out["text"] == "global hit"
    assert calls == [("my_notes", ""), ("", "")]


@pytest.mark.asyncio
async def test_impl_cli_fallback_when_api_empty(monkeypatch):
    async def fake_api(q, limit=5, wing="", room=""):
        return {"text": "", "sources": []}

    async def fake_cli(q, limit=5, wing="", room=""):
        return {"text": "cli hit", "sources": []}

    monkeypatch.setattr(pb, "_search_via_api", fake_api)
    monkeypatch.setattr(pb, "_search_via_cli", fake_cli)
    out = await pb._search_palace_context_impl("запрос", wing="projects")
    assert out["text"] == "cli hit"


@pytest.mark.asyncio
async def test_impl_propagates_cli_error(monkeypatch):
    async def empty(q, limit=5, wing="", room=""):
        return {"text": "", "sources": []}

    async def broken_cli(q, limit=5, wing="", room=""):
        return {"text": "", "sources": [], "error": True}

    monkeypatch.setattr(pb, "_search_via_api", empty)
    monkeypatch.setattr(pb, "_search_via_cli", broken_cli)
    out = await pb._search_palace_context_impl("запрос")
    assert out["text"] == ""
    assert out["error"] is True


# ---------- _rank_hits ----------


def test_rank_hits_empty():
    assert pb._rank_hits([]) == []


def test_rank_hits_sorts_by_combined_score():
    hits = [
        {"distance": 0.2, "bm25_score": 1.0},
        {"distance": 0.8, "bm25_score": 3.0},
        {"distance": 0.5, "bm25_score": 2.0},
    ]
    ranked = pb._rank_hits(hits)
    scores = [h["bm25_score"] for h in ranked]
    assert scores[0] > scores[-1]


def test_rank_hits_missing_bm25_all():
    hits = [{"distance": 0.3}, {"distance": 0.1}]
    ranked = pb._rank_hits(hits)
    assert ranked[0]["distance"] == 0.1
    assert ranked[1]["distance"] == 0.3


def test_rank_hits_bm25_max_zero_gives_one():
    hits = [{"distance": 0.4, "bm25_score": 0}, {"distance": None, "bm25_score": 2}]
    ranked = pb._rank_hits(hits)
    assert ranked[0]["bm25_score"] == 2


def test_rank_hits_all_zero_bm25_uses_one():
    hits = [
        {"distance": 0.3, "bm25_score": 0},
        {"distance": 0.5, "bm25_score": 0},
    ]
    ranked = pb._rank_hits(hits)
    assert ranked[0]["distance"] == 0.3
    assert ranked[1]["distance"] == 0.5


def test_rank_hits_no_distance_no_bm25():
    hits = [{"foo": 1}, {"foo": 2}]
    ranked = pb._rank_hits(hits)
    assert len(ranked) == 2


# ---------- _search_via_api ----------


@pytest.mark.asyncio
async def test_api_import_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name.startswith("mempalace"):
            raise ImportError("no mempalace")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert await pb._search_via_api("q") == {"text": "", "sources": []}


class FakeSearcherResult:
    def __init__(self, hits):
        self._hits = hits

    def get(self, key, default=None):
        if key == "results":
            return self._hits
        return default


def _async_empty_rooms(q, sources, limit=2):
    async def inner():
        return ""
    return inner()


def _patch_mempalace_modules(monkeypatch):
    import sys

    search_module = type(sys)("mempalace.searcher")
    search_module.search_memories = lambda *a, **k: None
    config_module = type(sys)("mempalace.config")
    config_module.MempalaceConfig = _FakeMempalaceConfig
    monkeypatch.setitem(sys.modules, "mempalace", type(sys)("mempalace"))
    monkeypatch.setitem(sys.modules, "mempalace.searcher", search_module)
    monkeypatch.setitem(sys.modules, "mempalace.config", config_module)


class _FakeMempalaceConfig:
    palace_path = "/tmp/palace"
    collection_name = "notes"


@pytest.mark.asyncio
async def test_api_no_results(monkeypatch):
    _patch_mempalace_modules(monkeypatch)
    monkeypatch.setattr(
        pb.asyncio, "get_event_loop",
        lambda: _FakeLoop(FakeSearcherResult([])),
    )
    assert await pb._search_via_api("q") == {"text": "", "sources": []}


@pytest.mark.asyncio
async def test_api_filters_bad_hits(monkeypatch):
    _patch_mempalace_modules(monkeypatch)
    hits = [
        {"bm25_score": 0.0, "distance": 0.1, "text": "drop"},
        {"bm25_score": 5.0, "distance": 0.9, "text": "drop2"},
        {"bm25_score": 4.0, "distance": 0.2, "text": "keep"},
    ]
    monkeypatch.setattr(
        pb.asyncio, "get_event_loop",
        lambda: _FakeLoop(FakeSearcherResult(hits)),
    )
    out = await pb._search_via_api("q", limit=2)
    assert "keep" in out["text"]
    assert "drop" not in out["text"]


@pytest.mark.asyncio
async def test_api_filters_all_hits_out(monkeypatch):
    _patch_mempalace_modules(monkeypatch)
    hits = [
        {"bm25_score": 0.0, "distance": 0.1, "text": "drop1"},
        {"bm25_score": 5.0, "distance": 0.9, "text": "drop2"},
    ]
    monkeypatch.setattr(
        pb.asyncio, "get_event_loop",
        lambda: _FakeLoop(FakeSearcherResult(hits)),
    )
    assert await pb._search_via_api("q") == {"text": "", "sources": []}


class _FakeLoop:
    def __init__(self, result):
        self._result = result

    async def run_in_executor(self, *a):
        fn = a[-3]
        args = a[-2] if len(a) > 1 else ()
        return fn(*args) if callable(fn) else self._result


@pytest.mark.asyncio
async def test_api_exception(monkeypatch):
    import sys

    search_module = type(sys)("mempalace.searcher")

    def boom(*a, **k):
        raise RuntimeError("search failed")

    search_module.search_memories = boom
    config_module = type(sys)("mempalace.config")
    config_module.MempalaceConfig = _FakeMempalaceConfig
    monkeypatch.setitem(sys.modules, "mempalace", type(sys)("mempalace"))
    monkeypatch.setitem(sys.modules, "mempalace.searcher", search_module)
    monkeypatch.setitem(sys.modules, "mempalace.config", config_module)
    out = await pb._search_via_api("q")
    assert out["text"] == ""
    assert out.get("error") is True


# ---------- _search_via_cli ----------


class _FakeProc:
    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


class _FakeCreateSubprocess:
    def __init__(self, procs):
        self._procs = procs
        self.commands = []

    async def __call__(self, *cmd, **kwargs):
        self.commands.append(cmd)
        return self._procs.pop(0)


@pytest.mark.asyncio
async def test_cli_success(monkeypatch):
    runner = _FakeCreateSubprocess([
        _FakeProc(0, "текст из CLI".encode(), b""),
    ])
    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", runner)
    out = await pb._search_via_cli("запрос", limit=3, wing="w")
    assert out == {"text": "текст из CLI", "sources": []}
    assert "--wing" in runner.commands[0]


@pytest.mark.asyncio
async def test_cli_success_with_room(monkeypatch):
    runner = _FakeCreateSubprocess([
        _FakeProc(0, "результат".encode(), b""),
    ])
    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", runner)
    out = await pb._search_via_cli("запрос", wing="w", room="r")
    assert out["text"] == "результат"
    assert "--room" in runner.commands[0]


@pytest.mark.asyncio
async def test_cli_nonzero_returncode(monkeypatch):
    runner = _FakeCreateSubprocess([
        _FakeProc(1, b"", b"search crashed"),
    ])
    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", runner)
    out = await pb._search_via_cli("q")
    assert out["text"] == ""
    assert out.get("error") is True


@pytest.mark.asyncio
async def test_cli_no_results_message(monkeypatch):
    runner = _FakeCreateSubprocess([
        _FakeProc(0, b"No results found", b""),
    ])
    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", runner)
    assert await pb._search_via_cli("q") == {"text": "", "sources": []}


@pytest.mark.asyncio
async def test_cli_empty_output(monkeypatch):
    runner = _FakeCreateSubprocess([
        _FakeProc(0, b"", b""),
    ])
    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", runner)
    assert await pb._search_via_cli("q") == {"text": "", "sources": []}


@pytest.mark.asyncio
async def test_cli_wing_retry_global(monkeypatch):
    runner = _FakeCreateSubprocess([
        _FakeProc(0, "Ничего не найдено".encode(), b""),
        _FakeProc(0, "глобальный результат".encode(), b""),
    ])
    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", runner)
    out = await pb._search_via_cli("q", wing="w")
    assert out == {"text": "глобальный результат", "sources": []}
    assert len(runner.commands) == 2
    assert "--wing" not in runner.commands[1]


@pytest.mark.asyncio
async def test_cli_exception(monkeypatch):
    async def boom(*cmd, **kwargs):
        raise OSError("no such proc")

    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", boom)
    out = await pb._search_via_cli("q")
    assert out["text"] == ""
    assert out.get("error") is True


# ---------- _search_connected_rooms ----------


class _FakeMCP:
    def __init__(self, raw):
        self._raw = raw
        self.started = False
        self.calls = []

    async def start(self):
        self.started = True
        self.contract = True

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return self._raw


@pytest.mark.asyncio
async def test_connected_rooms_empty_without_sources():
    assert await pb._search_connected_rooms("q", []) == ""


@pytest.mark.asyncio
async def test_connected_rooms_follows_tunnels(monkeypatch):
    mcp = _FakeMCP(json.dumps([{
        "connected_wing": "math", "connected_room": "integrals", "label": "похоже",
    }]))
    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: mcp)

    async def fake_impl(q, limit=2, wing="", room=""):
        return {"text": f"запись в {wing}/{room}", "sources": []}

    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    out = await pb._search_connected_rooms("q", [{"wing": "physics", "room": "cores"}])
    assert "СВЯЗИ ПО ТУННЕЛЯМ" in out
    assert "математика" in out.lower() or "math/integrals" in out
    assert "похоже" in out
    assert mcp.calls == [
        ("mempalace_follow_tunnels", {"wing": "physics", "room": "cores"}),
    ]


@pytest.mark.asyncio
async def test_connected_rooms_skips_self_and_bad_keys(monkeypatch):
    mcp = _FakeMCP(json.dumps([{
        "connected_wing": "physics", "connected_room": "cores", "label": "",
    }]))
    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: mcp)
    out = await pb._search_connected_rooms("q", [{"wing": "physics", "room": "cores"}])
    assert out == ""


@pytest.mark.asyncio
async def test_connected_rooms_mcp_error_quietly_skips(monkeypatch, caplog):
    class BoomMCP:
        async def start(self):
            raise RuntimeError("mcp down")

        async def call_tool(self, name, args):
            return ""

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: BoomMCP())
    assert await pb._search_connected_rooms("q", [{"wing": "a", "room": "b"}]) == ""
    assert "[PALACE_TUNNELS]" in caplog.text


@pytest.mark.asyncio
async def test_connected_rooms_call_tool_error_skips_source(monkeypatch):
    class BoomToolMCP:
        async def start(self):
            self.started = True

        async def call_tool(self, name, args):
            raise RuntimeError("tool boom")

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: BoomToolMCP())
    assert await pb._search_connected_rooms(
        "q", [{"wing": "a", "room": "b"}, {"wing": "c", "room": "d"}],
    ) == ""


@pytest.mark.asyncio
async def test_connected_rooms_skips_missing_wing_or_room(monkeypatch):
    mcp = _FakeMCP(json.dumps([{
        "connected_wing": "math", "connected_room": "integrals", "label": "",
    }]))
    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: mcp)
    out = await pb._search_connected_rooms(
        "q", [{"wing": "", "room": "x"}, {"wing": "y", "room": ""}],
    )
    assert out == ""
    assert mcp.calls == []


@pytest.mark.asyncio
async def test_connected_rooms_empty_connection_and_label_variants(monkeypatch):
    mcp = _FakeMCP(json.dumps([
        {"connected_wing": "m1", "connected_room": "r1", "label": "помечено"},
        {"connected_wing": "m2", "connected_room": "r2", "label": ""},
    ]))
    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: mcp)

    async def fake_impl(q, limit=2, wing="", room=""):
        if wing == "m1":
            return {"text": "", "sources": []}
        return {"text": f"запись {wing}/{room}", "sources": []}

    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    out = await pb._search_connected_rooms("q", [{"wing": "w", "room": "r"}])
    assert "СВЯЗИ ПО ТУННЕЛЯМ" in out
    assert "m2/r2" in out
    assert "помечено" not in out


# ---------- search_with_kg ----------


@pytest.mark.asyncio
async def test_search_with_kg_no_text(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing=""):
        return {"text": "", "sources": []}

    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    assert await pb.search_with_kg("пусто") == ""


@pytest.mark.asyncio
async def test_search_with_kg_status_empty_is_available(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing=""):
        return {"text": "", "sources": []}

    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    assert await pb.search_with_kg_status("пусто") == ("", True)


@pytest.mark.asyncio
async def test_search_with_kg_status_backend_error_is_unavailable(
    monkeypatch, palace_cb,
):
    async def fake_impl(q, limit=5, wing=""):
        return {"text": "", "sources": [], "error": True}

    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    assert await pb.search_with_kg_status("пусто") == ("", False)


@pytest.mark.asyncio
async def test_search_with_kg_status_unexpected_exception_is_unavailable(
    monkeypatch, palace_cb,
):
    async def boom(q, limit=5, wing=""):
        raise RuntimeError("backend exploded")

    monkeypatch.setattr(pb, "_search_palace_context_impl", boom)
    assert await pb.search_with_kg_status("пусто") == ("", False)


@pytest.mark.asyncio
async def test_search_with_kg_plain_text(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing=""):
        return {"text": "запись", "sources": []}

    async def fake_rooms(q, sources, limit=2):
        return ""

    class FakeKG:
        async def start(self):
            pass

        async def call_tool(self, name, args):
            return json.dumps({"facts": []})

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeKG())
    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    monkeypatch.setattr(pb, "_search_connected_rooms", fake_rooms)
    out = await pb.search_with_kg("тема")
    assert "запись" in out
    assert "ИСТОЧНИКИ" not in out
    assert "КГ" not in out


@pytest.mark.asyncio
async def test_search_with_kg_with_facts(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing=""):
        return {"text": "запись", "sources": [{"id": 1, "wing": "w", "room": "r", "score": 0.5}]}

    class FakeKG:
        async def start(self):
            pass

        async def call_tool(self, name, args):
            return json.dumps({
                "facts": [
                    {"subject": "Макс", "predicate": "wrote", "object": "книгу"},
                    {"subject": "X", "predicate": "contains_idea", "object": "идея"},
                    {"subject": "Y", "predicate": "contains_quote", "object": "цитата"},
                    {"subject": "Z", "predicate": "topic", "object": "тема"},
                    {"subject": "N", "predicate": "custom_rel", "object": "obj"},
                ],
            })

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeKG())
    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    monkeypatch.setattr(pb, "_search_connected_rooms", _async_empty_rooms)
    out = await pb.search_with_kg("Макс")
    assert "[1] w/r (score: 0.500)" in out
    assert "СВЯЗИ ИЗ ГРАФА ЗНАНИЙ" in out
    assert "Макс написал: книгу" in out
    assert "→ идея" in out
    assert "→ цитата" in out
    assert "тема" in out
    assert "custom_rel" in out


@pytest.mark.asyncio
async def test_search_with_kg_empty_facts(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing=""):
        return {"text": "запись", "sources": []}

    class FakeKG:
        async def start(self):
            pass

        async def call_tool(self, name, args):
            return json.dumps({"facts": []})

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeKG())
    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    monkeypatch.setattr(pb, "_search_connected_rooms", _async_empty_rooms)
    out = await pb.search_with_kg("тема")
    assert "КГ" not in out


@pytest.mark.asyncio
async def test_search_with_kg_circuit_breaker_open(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing=""):
        return {"text": "запись", "sources": []}

    class FakeKG:
        async def start(self):
            pass

        async def call_tool(self, name, args):
            raise CircuitBreakerOpenError("mcp open")

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeKG())
    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    monkeypatch.setattr(pb, "_search_connected_rooms", _async_empty_rooms)
    out = await pb.search_with_kg("тема")
    assert "запись" in out
    assert "КГ" not in out


@pytest.mark.asyncio
async def test_search_with_kg_mcp_error(monkeypatch, palace_cb, caplog):
    async def fake_impl(q, limit=5, wing=""):
        return {"text": "запись", "sources": []}

    class BoomKG:
        async def start(self):
            raise RuntimeError("mcp down")

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: BoomKG())
    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    monkeypatch.setattr(pb, "_search_connected_rooms", _async_empty_rooms)
    out = await pb.search_with_kg("тема")
    assert "запись" in out
    assert "[PALACE_KG] Ошибка поиска KG" in caplog.text


@pytest.mark.asyncio
async def test_search_with_kg_tunnel_block_included(monkeypatch, palace_cb):
    async def fake_impl(q, limit=5, wing=""):
        return {"text": "запись", "sources": []}

    async def fake_rooms(q, sources, limit=2):
        return "\n--- СВЯЗИ ПО ТУННЕЛЯМ ---\nблок\n--- КОНЕЦ СВЯЗЕЙ ---\n"

    class FakeKG:
        async def start(self):
            pass

        async def call_tool(self, name, args):
            return json.dumps({"facts": []})

    monkeypatch.setattr(palace_mcp, "get_mcp", lambda: FakeKG())
    monkeypatch.setattr(pb, "_search_palace_context_impl", fake_impl)
    monkeypatch.setattr(pb, "_search_connected_rooms", fake_rooms)
    out = await pb.search_with_kg("тема")
    assert "СВЯЗИ ПО ТУННЕЛЯМ" in out
    assert "блок" in out


# ---------- export_chat_verbatim / export_note_verbatim ----------


def test_export_chat_verbatim_missing_file(tmp_path):
    assert pb.export_chat_verbatim(str(tmp_path / "nope.json"), "chat") is None


def test_export_chat_verbatim_no_messages(tmp_path):
    chat = tmp_path / "chat.json"
    chat.write_text(json.dumps({"messages": []}), encoding="utf-8")
    assert pb.export_chat_verbatim(str(chat), "chat") is None


def test_export_chat_verbatim_writes_file(tmp_path, monkeypatch):
    chat = tmp_path / "chat.json"
    chat.write_text(json.dumps({
        "messages": [
            {"role": "user", "content": "  привет  "},
            {"role": "assistant", "content": "здравствуй"},
            {"role": "user", "content": "   "},
        ],
    }), encoding="utf-8")
    sync_dir = tmp_path / "sync"
    sync_dir.mkdir()
    monkeypatch.setattr(pb, "PALACE_SYNC_DIR", str(sync_dir))
    out = pb.export_chat_verbatim(str(chat), "my_chat.json")
    assert out is not None
    text = (sync_dir / "my_chat_verbatim.txt").read_text(encoding="utf-8")
    assert "# Chat: my_chat.json" in text
    assert "[USER]\nпривет" in text
    assert "[AI]\nздравствуй" in text
    assert "   " not in text


def test_export_note_verbatim_missing(tmp_path):
    assert pb.export_note_verbatim(str(tmp_path / "nope.md")) is None


def test_export_note_verbatim_copies(tmp_path, monkeypatch):
    note = tmp_path / "note.md"
    note.write_text("содержимое", encoding="utf-8")
    sync_dir = tmp_path / "sync2"
    sync_dir.mkdir()
    monkeypatch.setattr(pb, "PALACE_SYNC_DIR", str(sync_dir))
    out = pb.export_note_verbatim(str(note))
    assert out == str(sync_dir / "note.md")
    assert (sync_dir / "note.md").read_text(encoding="utf-8") == "содержимое"


# ---------- _run_mempalace / palace commands ----------


@pytest.mark.asyncio
async def test_run_mempalace_impl_success(monkeypatch):
    runner = _FakeCreateSubprocess([_FakeProc(0, b"status ok", b"")])
    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", runner)
    out = await pb._run_mempalace_impl(["status"])
    assert out == "status ok"
    assert runner.commands[0] == (sys.executable, "-m", "mempalace", "status")


@pytest.mark.asyncio
async def test_run_mempalace_impl_error(monkeypatch):
    runner = _FakeCreateSubprocess([_FakeProc(1, b"", b"boom")])
    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", runner)
    assert await pb._run_mempalace_impl(["status"]) == "❌ boom"


@pytest.mark.asyncio
async def test_run_mempalace_impl_error_no_stderr(monkeypatch):
    runner = _FakeCreateSubprocess([_FakeProc(1, b"", b"")])
    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", runner)
    assert await pb._run_mempalace_impl(["status"]) == "❌ Ошибка выполнения команды."


@pytest.mark.asyncio
async def test_run_mempalace_circuit_breaker_open(monkeypatch, palace_cb):
    async def boom(*a):
        raise CircuitBreakerOpenError("open")

    monkeypatch.setattr(pb, "_run_mempalace_impl", boom)
    out = await pb._run_mempalace(["status"])
    assert "временно недоступен" in out


@pytest.mark.asyncio
async def test_run_mempalace_generic_error(monkeypatch, palace_cb):
    async def boom(*a):
        raise RuntimeError("bad")

    monkeypatch.setattr(pb, "_run_mempalace_impl", boom)
    assert await pb._run_mempalace(["status"]) == "❌ Ошибка: bad"


@pytest.mark.asyncio
async def test_palace_commands_pass_args(monkeypatch, palace_cb):
    calls = []

    async def fake_run(args):
        calls.append(args)
        return "ok"

    monkeypatch.setattr(pb, "_run_mempalace", fake_run)
    assert await pb.palace_status() == "ok"
    assert await pb.palace_mcp() == "ok"
    assert await pb.palace_wake_up() == "ok"
    assert await pb.palace_split() == "ok"
    assert await pb.palace_split("/tmp/x") == "ok"
    assert await pb.palace_compress() == "ok"
    assert await pb.palace_compact() == "ok"
    assert await pb.palace_repair() == "ok"
    assert calls == [
        ["status"], ["mcp"], ["wake-up"], ["split"], ["split", "/tmp/x"],
        ["compress"], ["compact"], ["repair", "--yes"],
    ]


@pytest.mark.asyncio
async def test_palace_instructions_contains_sections():
    out = await pb.palace_instructions()
    assert "Что такое Дворец" in out
    assert "Граф знаний" in out
    assert "Обслуживание" in out


# ---------- sync_to_palace ----------


@pytest.mark.asyncio
async def test_sync_to_palace_empty_dir(monkeypatch, palace_cb, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    out = await pb.sync_to_palace(str(empty))
    assert "Нет данных" in out


@pytest.mark.asyncio
async def test_sync_to_palace_missing_target(monkeypatch, palace_cb, tmp_path):
    out = await pb.sync_to_palace(str(tmp_path / "nope"))
    assert "Нет данных" in out


@pytest.mark.asyncio
async def test_sync_to_palace_impl_mine_success(monkeypatch, palace_cb, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("x", encoding="utf-8")
    sync_dir = tmp_path / "sync3"
    sync_dir.mkdir()
    monkeypatch.setattr(pb, "PALACE_SYNC_DIR", str(sync_dir))
    (sync_dir / "old.txt").write_text("old", encoding="utf-8")

    runner = _FakeCreateSubprocess([_FakeProc(0, b"mined", b"")])
    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", runner)
    out = await pb.sync_to_palace(str(src))
    assert "Синхронизация с MemPalace завершена" in out
    assert not list(sync_dir.iterdir())


@pytest.mark.asyncio
async def test_sync_to_palace_impl_mine_error(monkeypatch, palace_cb, tmp_path):
    src = tmp_path / "src2"
    src.mkdir()
    (src / "a.txt").write_text("x", encoding="utf-8")
    runner = _FakeCreateSubprocess([_FakeProc(1, b"", b"mine failed")])
    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", runner)
    out = await pb.sync_to_palace(str(src))
    assert "Ошибка синхронизации: mine failed" in out


@pytest.mark.asyncio
async def test_sync_to_palace_impl_sync_dir_not_dir(monkeypatch, palace_cb, tmp_path):
    src = tmp_path / "src4"
    src.mkdir()
    (src / "a.txt").write_text("x", encoding="utf-8")
    sync_file = tmp_path / "sync_file"
    sync_file.write_text("data", encoding="utf-8")
    monkeypatch.setattr(pb, "PALACE_SYNC_DIR", str(sync_file))

    runner = _FakeCreateSubprocess([_FakeProc(0, b"mined", b"")])
    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", runner)
    out = await pb.sync_to_palace(str(src))
    assert "Синхронизация с MemPalace завершена" in out


@pytest.mark.asyncio
async def test_sync_to_palace_impl_skips_subdirs_in_sync_dir(monkeypatch, palace_cb, tmp_path):
    src = tmp_path / "src5"
    src.mkdir()
    (src / "a.txt").write_text("x", encoding="utf-8")
    sync_dir = tmp_path / "sync5"
    sync_dir.mkdir()
    (sync_dir / "sub").mkdir()
    monkeypatch.setattr(pb, "PALACE_SYNC_DIR", str(sync_dir))

    runner = _FakeCreateSubprocess([_FakeProc(0, b"mined", b"")])
    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", runner)
    out = await pb.sync_to_palace(str(src))
    assert "Синхронизация с MemPalace завершена" in out
    assert (sync_dir / "sub").is_dir()


@pytest.mark.asyncio
async def test_sync_to_palace_impl_exception(monkeypatch, palace_cb, tmp_path):
    src = tmp_path / "src3"
    src.mkdir()
    (src / "a.txt").write_text("x", encoding="utf-8")

    async def boom(*cmd, **kwargs):
        raise OSError("proc failed")

    monkeypatch.setattr(pb.asyncio, "create_subprocess_exec", boom)
    out = await pb.sync_to_palace(str(src))
    assert "Ошибка вызова mine" in out


@pytest.mark.asyncio
async def test_sync_to_palace_circuit_breaker_open(monkeypatch, palace_cb, tmp_path):
    async def boom(*a):
        raise CircuitBreakerOpenError("open")

    monkeypatch.setattr(pb, "_sync_to_palace_impl", boom)
    out = await pb.sync_to_palace()
    assert "временно недоступна" in out


@pytest.mark.asyncio
async def test_sync_to_palace_generic_error(monkeypatch, palace_cb, tmp_path):
    async def boom(*a):
        raise ValueError("bad")

    monkeypatch.setattr(pb, "_sync_to_palace_impl", boom)
    out = await pb.sync_to_palace()
    assert "Ошибка синхронизации: bad" in out
