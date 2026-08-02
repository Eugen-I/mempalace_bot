import time

from services.semantic_cache import SemanticCache


class TestSemanticCache:
    def test_hits_increment_by_one_per_get(self):
        cache = SemanticCache()
        cache.set("q", "r")
        cache.get("q")
        cache.get("q")
        entry = cache._entries[cache._normalize("q")]
        assert entry.hits == 3

    def test_normalize_collapses_whitespace(self):
        cache = SemanticCache()
        assert cache._normalize("Что  такое   ИИ?") == "что такое ии?"

    def test_set_and_get(self):
        cache = SemanticCache()
        cache.set("What is AI?", "Artificial Intelligence")
        assert cache.get("What is AI?") == "Artificial Intelligence"

    def test_get_miss_returns_none(self):
        cache = SemanticCache()
        assert cache.get("nonexistent") is None

    def test_similar_query_hit(self):
        cache = SemanticCache(threshold=0.6)
        cache.set("What is AI?", "Artificial Intelligence")
        assert cache.get("what is ai") == "Artificial Intelligence"

    def test_below_threshold_miss(self):
        cache = SemanticCache(threshold=0.99)
        cache.set("What is AI?", "Artificial Intelligence")
        assert cache.get("Hello world") is None

    def test_exact_threshold_hit(self):
        cache = SemanticCache(threshold=1.0)
        cache.set("hello world", "response")
        assert cache.get("hello world") == "response"

    def test_empty_query_does_not_cache(self):
        cache = SemanticCache()
        cache.set("", "response")
        assert cache.get("") is None

    def test_empty_response_does_not_cache(self):
        cache = SemanticCache()
        cache.set("query", "")
        assert cache.get("query") is None

    def test_max_size_eviction(self):
        cache = SemanticCache(max_size=2)
        cache.set("q1", "r1")
        cache.set("q2", "r2")
        cache.set("q3", "r3")
        assert cache.get("q1") is None
        assert cache.get("q2") is not None or cache.get("q3") is not None

    def test_ttl_eviction(self):
        cache = SemanticCache(ttl=0)
        time.sleep(0.01)
        cache.set("query", "response")
        assert cache.get("query") is None

    def test_invalidate_single(self):
        cache = SemanticCache()
        cache.set("query", "response")
        cache.invalidate("query")
        assert cache.get("query") is None

    def test_invalidate_all(self):
        cache = SemanticCache()
        cache.set("q1", "r1")
        cache.set("q2", "r2")
        cache.invalidate()
        assert cache.get("q1") is None
        assert cache.get("q2") is None

    def test_stats(self):
        cache = SemanticCache()
        cache.set("q1", "r1")
        cache.set("q2", "r2")
        cache.get("q1")
        cache.get("q1")
        stats = cache.stats
        assert stats["size"] == 2
        assert stats["total_hits"] >= 2


class TestSemanticCacheMutants:
    def test_default_ttl_and_max_size(self):
        cache = SemanticCache()
        assert cache.ttl == 300
        assert cache.max_size == 200

    def test_entry_query_stored(self):
        from services.semantic_cache import SemanticCacheEntry

        entry = SemanticCacheEntry("мой запрос", "resp")
        assert entry.query == "мой запрос"

    def test_hits_increment_logged(self, caplog):
        cache = SemanticCache()
        cache.set("Привет мир", "resp")
        cache.get("Привет мир")
        with caplog.at_level("INFO", logger="SemanticCache"):
            cache.get("привет мир")
        assert "hits=3" in caplog.text

    def test_hit_query_truncated_to_60(self, caplog):
        cache = SemanticCache()
        long_query = "q" * 60 + "ХВОСТ"
        cache.set(long_query, "resp")
        with caplog.at_level("INFO", logger="SemanticCache"):
            cache.get(long_query)
        assert "ХВОСТ" not in caplog.text
        assert "query='%s'" % ("q" * 60) in caplog.text

    def test_eviction_by_timestamp_not_lexicographic(self):
        cache = SemanticCache(max_size=2)
        cache.set("z", "rz")
        cache.set("a", "ra")
        cache.set("c", "rc")
        assert cache.get("z") is None
        assert cache.get("a") == "ra"
        assert cache.get("c") == "rc"

    def test_entry_query_normalized_after_set(self):
        cache = SemanticCache()
        cache.set("Привет мир", "resp")
        assert cache.get("привет  мир") == "resp"

    def test_invalidate_all_logs_exact_message(self, caplog):
        cache = SemanticCache()
        cache.set("q1", "r1")
        with caplog.at_level("INFO", logger="SemanticCache"):
            cache.invalidate()
        assert caplog.records[-1].getMessage() == "Semantic cache cleared"

    def test_evict_expired_logs_exact_message(self, caplog):
        cache = SemanticCache(ttl=0)
        cache.set("q", "r")
        time.sleep(0.01)
        with caplog.at_level("DEBUG", logger="SemanticCache"):
            assert cache.get("q") is None
        assert caplog.records[-1].getMessage() == "Evicted 1 expired cache entries"
