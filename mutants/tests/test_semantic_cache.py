import time

from services.semantic_cache import SemanticCache


class TestSemanticCache:
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
