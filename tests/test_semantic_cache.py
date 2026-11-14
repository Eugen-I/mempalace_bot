import pytest

from services.semantic_cache import SemanticCache, SemanticCacheEntry


def _ctx(**overrides):
    context = {
        "chat_id": "chat-1",
        "wing": "dreams",
        "model": "model-a",
        "prompt_version": "prompt-v1",
        "mode": "chat",
    }
    context.update(overrides)
    return context


def _fake_time(monkeypatch, value: float = 1000.0):
    clock = [value]
    monkeypatch.setattr("services.semantic_cache.time.time", lambda: clock[0])
    return clock


class TestSemanticCache:
    def test_hits_increment_by_one_per_get(self):
        ctx = _ctx()
        cache = SemanticCache()
        cache.set("q", "r", **ctx)
        cache.get("q", **ctx)
        cache.get("q", **ctx)
        entry = next(e for e in cache._entries.values() if e.query == "q")
        assert entry.hits == 3

    def test_normalize_collapses_whitespace(self):
        cache = SemanticCache()
        assert cache._normalize("Что  такое   ИИ?") == "что такое ии?"

    def test_set_and_get(self):
        ctx = _ctx()
        cache = SemanticCache()
        cache.set("What is AI?", "Artificial Intelligence", **ctx)
        assert cache.get("What is AI?", **ctx) == "Artificial Intelligence"

    def test_get_miss_returns_none(self):
        cache = SemanticCache()
        assert cache.get("nonexistent", **_ctx()) is None

    def test_similar_query_hit(self):
        ctx = _ctx()
        cache = SemanticCache(threshold=0.6)
        cache.set("What is AI?", "Artificial Intelligence", **ctx)
        assert cache.get("what is ai", **ctx) == "Artificial Intelligence"

    def test_below_threshold_miss(self):
        ctx = _ctx()
        cache = SemanticCache(threshold=0.99)
        cache.set("What is AI?", "Artificial Intelligence", **ctx)
        assert cache.get("Hello world", **ctx) is None

    def test_exact_threshold_hit(self):
        ctx = _ctx()
        cache = SemanticCache(threshold=1.0)
        cache.set("hello world", "response", **ctx)
        assert cache.get("hello world", **ctx) == "response"

    def test_empty_query_does_not_cache(self):
        cache = SemanticCache()
        cache.set("", "response", **_ctx())
        assert cache.get("", **_ctx()) is None

    def test_empty_response_does_not_cache(self):
        ctx = _ctx()
        cache = SemanticCache()
        cache.set("query", "", **ctx)
        assert cache.get("query", **ctx) is None

    def test_whitespace_only_query_does_not_cache(self):
        ctx = _ctx()
        cache = SemanticCache()
        cache.set("   ", "response", **ctx)
        assert cache.stats["size"] == 0

    def test_max_size_eviction(self, monkeypatch):
        clock = _fake_time(monkeypatch)
        ctx = _ctx()
        cache = SemanticCache(max_size=2)
        cache.set("q1", "r1", **ctx)
        clock[0] += 1
        cache.set("q2", "r2", **ctx)
        clock[0] += 1
        cache.set("q3", "r3", **ctx)
        assert cache.get("q1", **ctx) is None
        assert cache.get("q2", **ctx) == "r2"
        assert cache.get("q3", **ctx) == "r3"

    def test_ttl_eviction(self, monkeypatch):
        clock = _fake_time(monkeypatch)
        ctx = _ctx()
        cache = SemanticCache(ttl=1)
        cache.set("query", "response", **ctx)
        clock[0] = 1001.1
        assert cache.get("query", **ctx) is None

    def test_ttl_refreshes_on_hit(self, monkeypatch):
        clock = _fake_time(monkeypatch)
        ctx = _ctx()
        cache = SemanticCache(ttl=10)
        cache.set("query", "response", **ctx)
        clock[0] = 1009.0
        assert cache.get("query", **ctx) == "response"
        clock[0] = 1015.0
        assert cache.get("query", **ctx) == "response"
        clock[0] = 1026.0
        assert cache.get("query", **ctx) is None

    def test_invalidate_single(self):
        ctx = _ctx()
        cache = SemanticCache()
        cache.set("query", "response", **ctx)
        cache.invalidate("query")
        assert cache.get("query", **ctx) is None

    def test_invalidate_all(self):
        ctx = _ctx()
        cache = SemanticCache()
        cache.set("q1", "r1", **ctx)
        cache.set("q2", "r2", **ctx)
        cache.invalidate()
        assert cache.get("q1", **ctx) is None
        assert cache.get("q2", **ctx) is None

    def test_stats(self):
        ctx = _ctx()
        cache = SemanticCache()
        cache.set("q1", "r1", **ctx)
        cache.set("q2", "r2", **ctx)
        cache.get("q1", **ctx)
        cache.get("q1", **ctx)
        stats = cache.stats
        assert stats["size"] == 2
        assert stats["total_hits"] >= 2


class TestSemanticCacheScope:
    def test_same_query_different_chats_isolated(self):
        cache = SemanticCache()
        cache.set("q", "chat-1 answer", **_ctx(chat_id="chat-1"))
        assert cache.get("q", **_ctx(chat_id="chat-2")) is None

    def test_same_query_different_wings_isolated(self):
        cache = SemanticCache()
        cache.set("q", "dreams answer", **_ctx(wing="dreams"))
        assert cache.get("q", **_ctx(wing="projects")) is None

    def test_same_query_different_models_isolated(self):
        cache = SemanticCache()
        cache.set("q", "model-a answer", **_ctx(model="model-a"))
        assert cache.get("q", **_ctx(model="model-b")) is None

    def test_same_query_different_prompt_versions_isolated(self):
        cache = SemanticCache()
        cache.set("q", "v1 answer", **_ctx(prompt_version="prompt-v1"))
        assert cache.get("q", **_ctx(prompt_version="prompt-v2")) is None

    def test_same_query_different_modes_isolated(self):
        cache = SemanticCache()
        cache.set("q", "chat answer", **_ctx(mode="chat"))
        assert cache.get("q", **_ctx(mode="coding")) is None

    def test_similarity_does_not_cross_scopes(self):
        cache = SemanticCache(threshold=0.6)
        cache.set("What is AI?", "chat-1 answer", **_ctx(chat_id="chat-1"))
        assert cache.get("what is ai", **_ctx(chat_id="chat-2")) is None

    def test_missing_context_never_uses_global_cache(self):
        cache = SemanticCache()
        cache.set("q", "r")
        assert cache.get("q") is None
        assert cache.stats["size"] == 0

    @pytest.mark.parametrize(
        "missing", ["chat_id", "wing", "model", "prompt_version"],
    )
    def test_missing_scope_component_misses(self, missing):
        cache = SemanticCache()
        cache.set("q", "r", **_ctx())
        invalid = _ctx(**{missing: None})
        assert cache.get("q", **invalid) is None

    @pytest.mark.parametrize("missing", ["wing", "model", "prompt_version"])
    def test_empty_scope_component_does_not_store(self, missing):
        cache = SemanticCache()
        cache.set("q", "r", **_ctx(**{missing: ""}))
        assert cache.stats["size"] == 0

    def test_model_invalidation_removes_only_target_model(self):
        cache = SemanticCache()
        cache.set("q", "old", **_ctx(model="model-a"))
        cache.set("q", "new", **_ctx(model="model-b"))
        assert cache.invalidate_model("model-a") == 1
        assert cache.get("q", **_ctx(model="model-a")) is None
        assert cache.get("q", **_ctx(model="model-b")) == "new"

    def test_model_invalidation_empty_model_is_noop(self):
        cache = SemanticCache()
        cache.set("q", "r", **_ctx())
        assert cache.invalidate_model("") == 0
        assert cache.get("q", **_ctx()) == "r"

    def test_model_invalidation_unknown_model_is_noop(self):
        cache = SemanticCache()
        cache.set("q", "r", **_ctx())
        assert cache.invalidate_model("model-x") == 0
        assert cache.get("q", **_ctx()) == "r"


class TestSemanticCacheMutants:
    def test_default_ttl_and_max_size(self):
        cache = SemanticCache()
        assert cache.ttl == 300
        assert cache.max_size == 200

    def test_entry_query_stored(self):
        entry = SemanticCacheEntry("мой запрос", "resp")
        assert entry.query == "мой запрос"

    def test_hits_increment_logged(self, caplog):
        ctx = _ctx()
        cache = SemanticCache()
        cache.set("Привет мир", "resp", **ctx)
        cache.get("Привет мир", **ctx)
        with caplog.at_level("INFO", logger="SemanticCache"):
            cache.get("привет мир", **ctx)
        assert "hits=3" in caplog.text

    def test_hit_query_truncated_to_60(self, caplog):
        ctx = _ctx()
        cache = SemanticCache()
        long_query = "q" * 60 + "ХВОСТ"
        cache.set(long_query, "resp", **ctx)
        with caplog.at_level("INFO", logger="SemanticCache"):
            cache.get(long_query, **ctx)
        assert "ХВОСТ" not in caplog.text
        assert "query='%s'" % ("q" * 60) in caplog.text

    def test_eviction_by_timestamp_not_lexicographic(self, monkeypatch):
        clock = _fake_time(monkeypatch)
        ctx = _ctx()
        cache = SemanticCache(max_size=2)
        cache.set("z", "rz", **ctx)
        clock[0] += 1
        cache.set("a", "ra", **ctx)
        clock[0] += 1
        cache.set("c", "rc", **ctx)
        assert cache.get("z", **ctx) is None
        assert cache.get("a", **ctx) == "ra"
        assert cache.get("c", **ctx) == "rc"

    def test_entry_query_normalized_after_set(self):
        ctx = _ctx()
        cache = SemanticCache()
        cache.set("Привет мир", "resp", **ctx)
        assert cache.get("привет  мир", **ctx) == "resp"

    def test_invalidate_all_logs_exact_message(self, caplog):
        ctx = _ctx()
        cache = SemanticCache()
        cache.set("q1", "r1", **ctx)
        with caplog.at_level("INFO", logger="SemanticCache"):
            cache.invalidate()
        assert caplog.records[-1].getMessage() == "Semantic cache cleared"

    def test_evict_expired_logs_exact_message(self, caplog, monkeypatch):
        clock = _fake_time(monkeypatch)
        ctx = _ctx()
        cache = SemanticCache(ttl=1)
        cache.set("q", "r", **ctx)
        clock[0] = 1001.1
        with caplog.at_level("DEBUG", logger="SemanticCache"):
            assert cache.get("q", **ctx) is None
        assert caplog.records[-1].getMessage() == "Evicted 1 expired cache entries"

    def test_evict_boundary_exact_ttl_is_not_expired(self, monkeypatch):
        clock = _fake_time(monkeypatch)
        ctx = _ctx()
        cache = SemanticCache(ttl=100)
        cache.set("q", "r", **ctx)
        clock[0] = 1100.0
        assert cache.get("q", **ctx) == "r"
        assert cache.stats["size"] == 1

    def test_get_equal_scores_keeps_first_entry(self, monkeypatch):
        ctx = _ctx()
        cache = SemanticCache(threshold=0.5)
        cache.set("first key", "r1", **ctx)
        cache.set("second key", "r2", **ctx)
        monkeypatch.setattr(cache, "_similarity", lambda a, b: 0.9)
        assert cache.get("q", **ctx) == "r1"

    def test_set_stores_normalized_query(self):
        ctx = _ctx()
        cache = SemanticCache()
        cache.set("  What   Is   AI? ", "r", **ctx)
        entry = next(e for e in cache._entries.values() if e.query == "what is ai?")
        assert entry.query == "what is ai?"

    def test_invalidate_missing_key_no_keyerror(self):
        cache = SemanticCache()
        cache.invalidate("несуществующий")
